"""QQ NT passphrase diagnostics.

This module does not print or persist the database passphrase. It only locates
the runtime hook point and checks whether macOS allows attaching to the user's
own QQ process.
"""

from __future__ import annotations

import platform
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

QQ_APP = "/Applications/QQ.app/Contents/MacOS/QQ"
QQ_BUNDLE = "/Applications/QQ.app"
WRAPPER_NODE = "/Applications/QQ.app/Contents/Resources/app/wrapper.node"
WECHAT_BUNDLES = [
    "/Applications/WeChat.app",
    "/Applications/微信.app",
    "/Applications/Weixin.app",
]


def diagnose_key_access() -> Dict[str, Any]:
    pid = find_qq_pid()
    wrapper = Path(WRAPPER_NODE)
    arch = platform.machine()
    offset = locate_nt_key_function_offset(wrapper, arch=arch) if wrapper.exists() else None
    attach = probe_lldb_attach(pid) if pid else {"status": "qq_not_running"}
    sip = get_sip_status()
    apps = diagnose_app_versions()
    compatibility = assess_version_compatibility(apps, wrapper.exists(), bool(offset))
    return {
        "status": "ok" if pid and offset and attach.get("status") == "attach_ok" else "blocked_or_incomplete",
        "qq_pid": pid,
        "arch": arch,
        "sip": sip,
        "apps": apps,
        "compatibility": compatibility,
        "wrapper_node": str(wrapper),
        "wrapper_exists": wrapper.exists(),
        "nt_sqlite3_key_v2_offset": f"0x{offset:x}" if offset else None,
        "lldb_attach": attach,
        "flash_guide": build_flash_guide(sip, attach, compatibility),
        "safe_next_step": _next_step(attach, sip=sip, compatibility=compatibility),
        "privacy": {
            "prints_passphrase": False,
            "stores_passphrase": False,
        },
    }


def capture_passphrase(out_path: Path, *, timeout: int = 120) -> Dict[str, Any]:
    """Capture QQ NT SQLCipher passphrase to a local 0600 file.

    The passphrase is never printed. If macOS denies debugger attachment, the
    function returns an explicit blocked status.
    """
    pid = find_qq_pid()
    wrapper = Path(WRAPPER_NODE)
    arch = platform.machine()
    offset = locate_nt_key_function_offset(wrapper, arch=arch) if wrapper.exists() else None
    if not pid:
        return {"status": "qq_not_running", "message": "未发现 QQ 主进程"}
    if not offset:
        return {"status": "offset_not_found", "message": "未能定位 nt_sqlite3_key_v2 偏移"}

    out_path = out_path.expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path = out_path.with_suffix(out_path.suffix + ".captured")
    for path in (out_path, marker_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    command_file = _build_lldb_capture_script(pid, offset, arch, out_path, marker_path)
    try:
        proc = subprocess.run(
            ["lldb", "-b", "-s", str(command_file)],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "message": "等待 passphrase 超时；请保持 QQ 登录并点击任意聊天会话后重试。",
            "passphrase_file": str(out_path),
        }
    finally:
        try:
            command_file.unlink()
        except Exception:
            pass

    output = (proc.stdout or "") + (proc.stderr or "")
    if out_path.exists() and out_path.stat().st_size > 0:
        try:
            out_path.chmod(0o600)
        except OSError:
            pass
        return {
            "status": "captured",
            "passphrase_file": str(out_path),
            "bytes": out_path.stat().st_size,
            "message": "已捕获 passphrase 到本机受限权限文件；未在终端输出密钥。",
        }
    if "Not allowed to attach" in output:
        sip = get_sip_status()
        return {
            "status": "attach_denied",
            "message": "macOS 拒绝附加 QQ 进程。请先按 flash_guide 处理 SIP/调试权限后重试。",
            "sip": sip,
            "flash_guide": build_flash_guide(
                sip,
                {"status": "attach_denied"},
                assess_version_compatibility(diagnose_app_versions(), wrapper.exists(), bool(offset)),
            ),
        }
    compact = " ".join(output.split())
    return {
        "status": "failed",
        "message": compact[:700] or "LLDB 未捕获到 passphrase",
        "passphrase_file": str(out_path),
    }


def find_qq_pid() -> Optional[int]:
    try:
        output = subprocess.check_output(["ps", "-axo", "pid,command"], text=True)
    except Exception:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        if parts[1] == QQ_APP:
            return int(parts[0])
    return None


def locate_nt_key_function_offset(wrapper_path: Path, *, arch: Optional[str] = None) -> Optional[int]:
    if not wrapper_path.exists():
        return None
    objdump_arch = "arm64" if (arch or "").lower() in {"arm64", "aarch64"} else "x86_64"
    try:
        proc = subprocess.Popen(
            ["objdump", "-d", f"--arch={objdump_arch}", str(wrapper_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None

    previous: List[str] = []
    target_line: Optional[str] = None
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="ignore")
            if 'literal pool for: "nt_sqlite3_key_v2: db=%p zDb=%s"' in line:
                target_line = line
                break
            if _instruction_address(line) is not None:
                previous.append(line)
                previous = previous[-120:]
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
    if not target_line:
        return None
    return _nearest_function_start(previous)


def probe_lldb_attach(pid: Optional[int]) -> Dict[str, Any]:
    if not pid:
        return {"status": "qq_not_running", "message": "未发现 QQ 主进程"}
    try:
        proc = subprocess.run(
            ["lldb", "-p", str(pid), "-o", "detach", "-o", "quit"],
            text=True,
            capture_output=True,
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "attach_timeout", "message": "LLDB 附加超时"}
    except OSError as exc:
        return {"status": "lldb_missing", "message": str(exc)}
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0 and "error: attach failed" not in output:
        return {"status": "attach_ok", "message": "LLDB 可以附加 QQ 进程"}
    compact = " ".join(output.split())
    if "Not allowed to attach" in compact:
        return {
            "status": "attach_denied",
            "message": "macOS 拒绝附加 QQ 进程，通常需要 Developer Tools 权限或调整 SIP/调试权限。",
        }
    return {"status": "attach_failed", "message": compact[:500]}


def get_sip_status() -> Dict[str, Any]:
    """Return a product-facing SIP status summary.

    macOS only allows changing SIP from Recovery OS. This function never tries
    to change SIP; it only reports whether the current boot can attach to
    hardened apps such as QQ/WeChat.
    """
    if platform.system() != "Darwin":
        return {
            "status": "not_macos",
            "enabled": False,
            "requires_recovery_to_change": False,
            "can_disable_while_booted": False,
            "message": "非 macOS，不适用 SIP。",
        }
    try:
        proc = subprocess.run(
            ["csrutil", "status"],
            text=True,
            capture_output=True,
            timeout=6,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "unknown",
            "enabled": None,
            "requires_recovery_to_change": True,
            "can_disable_while_booted": False,
            "message": f"无法读取 SIP 状态：{exc}",
            "minimal_steps": _minimal_sip_steps(),
        }

    raw = ((proc.stdout or "") + (proc.stderr or "")).strip()
    lowered = raw.lower()
    if "disabled" in lowered:
        status = "disabled"
        enabled: Optional[bool] = False
    elif "enabled" in lowered:
        status = "enabled"
        enabled = True
    else:
        status = "unknown"
        enabled = None
    data: Dict[str, Any] = {
        "status": status,
        "enabled": enabled,
        "requires_recovery_to_change": True,
        "can_disable_while_booted": False,
        "message": raw or "未返回 SIP 状态。",
    }
    if enabled is not False:
        data["minimal_steps"] = _minimal_sip_steps()
    return data


def diagnose_app_versions() -> Dict[str, Any]:
    wechat_apps = [_read_app_info(Path(path)) for path in WECHAT_BUNDLES if Path(path).exists()]
    return {
        "qq": _read_app_info(Path(QQ_BUNDLE)),
        "wechat": {
            "installed": bool(wechat_apps),
            "primary": wechat_apps[0] if wechat_apps else None,
            "candidates": wechat_apps,
        },
    }


def assess_version_compatibility(
    apps: Dict[str, Any],
    wrapper_exists: bool,
    offset_found: bool,
) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    qq = apps.get("qq") or {}
    qq_version = qq.get("version")
    qq_ready = False
    if not qq.get("installed"):
        items.append({
            "app": "QQ",
            "level": "block",
            "message": "未发现 /Applications/QQ.app；无法采集当前 Mac QQ。",
        })
    elif not wrapper_exists:
        items.append({
            "app": "QQ",
            "level": "block",
            "message": "未发现 QQ NT wrapper.node；当前 QQ 版本/安装形态不是已支持的 NT 路径。",
        })
    elif not offset_found:
        items.append({
            "app": "QQ",
            "level": "block",
            "message": "未定位 nt_sqlite3_key_v2；QQ 版本可能已变更，需要先适配密钥捕获点。",
        })
    else:
        qq_ready = True
        items.append({
            "app": "QQ",
            "level": "pass",
            "version": qq_version,
            "message": "QQ NT 关键文件和 passphrase 捕获点已定位；剩余卡点是 macOS 调试/SIP 权限。",
        })

    if qq_version and not _version_at_least(qq_version, "6.0.0"):
        items.append({
            "app": "QQ",
            "level": "warn",
            "version": qq_version,
            "message": "QQ 版本低于当前 NT 主路径口径，解密后仍需做联系人/群/消息表验证。",
        })

    wechat = apps.get("wechat") or {}
    primary_wechat = wechat.get("primary") or {}
    wx_version = primary_wechat.get("version")
    wechat_runtime_verify = bool(primary_wechat)
    if not primary_wechat:
        items.append({
            "app": "WeChat",
            "level": "info",
            "message": "未发现 /Applications/WeChat.app；本次 QQ 诊断不受影响。",
        })
    elif wx_version and _version_at_least(wx_version, "4.1.0"):
        items.append({
            "app": "WeChat",
            "level": "warn",
            "version": wx_version,
            "message": "微信 4.1+ 旧式内存扫描不可用；必须走 Mac 4.x hook 路径，并以 key 匹配库数量和真实读取结果为准。",
        })
    elif wx_version and _version_at_least(wx_version, "4.0.0"):
        items.append({
            "app": "WeChat",
            "level": "pass",
            "version": wx_version,
            "message": "微信 4.x 属于当前采集器 Mac hook 路径；关闭 SIP 后仍要用提取器结果复验。",
        })
    elif wx_version:
        items.append({
            "app": "WeChat",
            "level": "warn",
            "version": wx_version,
            "message": "微信版本低于 4.x，当前项目主路径已转向 4.x；需要单独验证旧库支持情况。",
        })

    return {
        "qq_key_path_ready": qq_ready,
        "wechat_requires_runtime_verification": wechat_runtime_verify,
        "items": items,
    }


def build_flash_guide(
    sip: Dict[str, Any],
    attach: Dict[str, Any],
    compatibility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if sip.get("enabled") is True:
        return {
            "show": True,
            "code": "SIP_ENABLED_BLOCKS_KEY_CAPTURE",
            "severity": "blocked",
            "title": "SIP 已开启：当前无法捕获 QQ/微信数据库密钥",
            "can_disable_without_reboot": False,
            "summary": "macOS 只能在恢复环境修改 SIP；正常开机状态下不能关闭。",
            "minimal_steps": _minimal_sip_steps(),
            "after_steps": [
                "回到桌面后打开并登录 QQ。",
                "重新运行 key-diagnose，看到 lldb_attach 为 attach_ok 后再运行 key-capture。",
                "采集完成后建议同样进入恢复环境执行 csrutil enable 恢复 SIP。",
            ],
        }
    if attach.get("status") == "attach_denied":
        return {
            "show": True,
            "code": "DEBUG_ATTACH_DENIED",
            "severity": "blocked",
            "title": "系统仍拒绝调试 QQ 进程",
            "summary": "如果 SIP 已关闭，请确认终端/运行环境有开发者工具权限，然后重新运行 key-diagnose。",
            "minimal_steps": [
                "打开 系统设置。",
                "到 隐私与安全性 / 开发者工具，允许当前终端或 Codex 运行环境。",
                "保持 QQ 登录，重新运行 key-diagnose。",
            ],
        }
    if compatibility and not compatibility.get("qq_key_path_ready"):
        return {
            "show": True,
            "code": "QQ_VERSION_NEEDS_ADAPTATION",
            "severity": "blocked",
            "title": "QQ 版本/安装形态需要先适配",
            "summary": "当前没有定位到可用的 QQ NT 密钥捕获点，关闭 SIP 也可能无法继续。",
            "minimal_steps": [
                "确认已安装并登录最新版 QQ。",
                "重新运行 probe 和 key-diagnose。",
                "如果仍提示未定位捕获点，需要先适配当前 QQ 版本。",
            ],
        }
    return {
        "show": False,
        "code": "READY_OR_NON_MACOS",
        "severity": "info",
        "title": "未发现需要闪光提示的系统阻断项",
    }


def _minimal_sip_steps() -> List[str]:
    if platform.machine().lower() in {"arm64", "aarch64"}:
        recovery_step = "Apple 芯片：关机后长按电源键，直到出现“启动选项”，点“选项”进入恢复环境。"
    else:
        recovery_step = "Intel Mac：重启后立刻按住 Command + R，进入恢复环境。"
    return [
        "保存工作，准备重启 Mac。",
        recovery_step,
        "在顶部菜单打开“实用工具” > “终端”。",
        "输入 csrutil disable，按提示确认，然后重启回桌面。",
        "采集完成后，建议同样进入恢复环境输入 csrutil enable 恢复 SIP。",
    ]


def _read_app_info(bundle_path: Path) -> Dict[str, Any]:
    plist = bundle_path / "Contents" / "Info.plist"
    installed = bundle_path.exists()
    data: Dict[str, Any] = {
        "installed": installed,
        "path": str(bundle_path),
    }
    if not installed:
        return data
    data.update({
        "bundle_id": _plist_value(plist, "CFBundleIdentifier"),
        "name": _plist_value(plist, "CFBundleName") or bundle_path.stem,
        "version": _plist_value(plist, "CFBundleShortVersionString"),
        "build": _plist_value(plist, "CFBundleVersion"),
    })
    return data


def _plist_value(plist: Path, key: str) -> Optional[str]:
    if not plist.exists():
        return None
    try:
        proc = subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", f"Print :{key}", str(plist)],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def _version_at_least(version: str, minimum: str) -> bool:
    return _version_tuple(version) >= _version_tuple(minimum)


def _version_tuple(version: str) -> tuple:
    parts = [int(item) for item in re.findall(r"\d+", version or "")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _build_lldb_capture_script(pid: int, offset: int, arch: str, out_path: Path, marker_path: Path) -> Path:
    pointer_register = "x2" if arch.lower() in {"arm64", "aarch64"} else "rdx"
    length_register = "x3" if arch.lower() in {"arm64", "aarch64"} else "rcx"
    out_literal = repr(str(out_path))
    marker_literal = repr(str(marker_path))
    capture_code = (
        "import os,lldb;"
        "fr=lldb.frame;"
        "proc=fr.GetThread().GetProcess();"
        f"addr=fr.FindRegister('{pointer_register}').GetValueAsUnsigned();"
        f"size=fr.FindRegister('{length_register}').GetValueAsUnsigned();"
        "err=lldb.SBError();"
        "data=proc.ReadMemory(addr,size,err);"
        "ok=err.Success() and data and 8<=len(data)<=128;"
        f"open({out_literal},'wb').write(data if ok else b'');"
        f"os.chmod({out_literal},0o600);"
        f"open({marker_literal},'w').write('captured' if ok else 'empty');"
        "print('QQ_NT_PASSPHRASE_CAPTURED' if ok else 'QQ_NT_PASSPHRASE_EMPTY');"
        "lldb.debugger.HandleCommand('process detach');"
        "lldb.debugger.HandleCommand('quit')"
    )
    script = "\n".join(
        [
            f"process attach --pid {pid}",
            "breakpoint delete --force",
            (
                "script target=lldb.debugger.GetSelectedTarget();"
                "mods=[m for m in target.module_iter() if 'wrapper.node' in str(m.file)];"
                f"base=mods[0].GetObjectFileHeaderAddress().GetLoadAddress(target);"
                f"lldb.debugger.HandleCommand('breakpoint set --address 0x%x' % (base+{offset}))"
            ),
            f"breakpoint command add 1 --one-liner \"script {capture_code}\"",
            "continue",
            "",
        ]
    )
    handle = tempfile.NamedTemporaryFile("w", delete=False, prefix="collectorx-qq-key-", suffix=".lldb")
    try:
        handle.write(script)
        return Path(handle.name)
    finally:
        handle.close()


def _nearest_function_start(lines: List[str]) -> Optional[int]:
    for line in reversed(lines):
        if "sub\tsp, sp" in line or "pushq" in line:
            return _instruction_address(line)
    return None


def _instruction_address(line: str) -> Optional[int]:
    match = re.match(r"\s*([0-9a-fA-F]+):", line)
    if not match:
        return None
    return int(match.group(1), 16)


def _next_step(
    attach: Dict[str, Any],
    *,
    sip: Optional[Dict[str, Any]] = None,
    compatibility: Optional[Dict[str, Any]] = None,
) -> str:
    status = attach.get("status")
    if sip and sip.get("enabled") is True:
        return "SIP 已开启，正常开机状态无法关闭。请按 flash_guide 进入恢复环境关闭 SIP，再回到桌面重新运行 key-diagnose。"
    if compatibility and not compatibility.get("qq_key_path_ready"):
        return "QQ 版本/安装形态尚未定位到可用密钥捕获点；请先按 compatibility 提示适配版本。"
    if status == "attach_ok":
        return "可以继续运行受保护的 key-hook 流程；捕获到 passphrase 后只写入本机安全文件。"
    if status == "attach_denied":
        return "系统阻止自动取 passphrase。请按 flash_guide 处理 SIP/调试权限后，重新运行 key-diagnose。"
    if status == "qq_not_running":
        return "先启动并登录 QQ，再运行 key-diagnose。"
    return "先处理 LLDB/权限问题，再继续解密链路。"


__all__ = [
    "capture_passphrase",
    "assess_version_compatibility",
    "build_flash_guide",
    "diagnose_key_access",
    "diagnose_app_versions",
    "find_qq_pid",
    "get_sip_status",
    "locate_nt_key_function_offset",
    "probe_lldb_attach",
]
