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
WRAPPER_NODE = "/Applications/QQ.app/Contents/Resources/app/wrapper.node"


def diagnose_key_access() -> Dict[str, Any]:
    pid = find_qq_pid()
    wrapper = Path(WRAPPER_NODE)
    arch = platform.machine()
    offset = locate_nt_key_function_offset(wrapper, arch=arch) if wrapper.exists() else None
    attach = probe_lldb_attach(pid) if pid else {"status": "qq_not_running"}
    return {
        "status": "ok" if pid and offset and attach.get("status") == "attach_ok" else "blocked_or_incomplete",
        "qq_pid": pid,
        "arch": arch,
        "wrapper_node": str(wrapper),
        "wrapper_exists": wrapper.exists(),
        "nt_sqlite3_key_v2_offset": f"0x{offset:x}" if offset else None,
        "lldb_attach": attach,
        "safe_next_step": _next_step(attach),
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
        return {
            "status": "attach_denied",
            "message": "macOS 拒绝附加 QQ 进程。请先在系统设置中启用开发者工具权限，必要时处理 SIP。",
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


def _next_step(attach: Dict[str, Any]) -> str:
    status = attach.get("status")
    if status == "attach_ok":
        return "可以继续运行受保护的 key-hook 流程；捕获到 passphrase 后只写入本机安全文件。"
    if status == "attach_denied":
        return "系统阻止自动取 passphrase。需要在本机授予调试权限/按项目文档处理 SIP 后，重新运行 key-diagnose。"
    if status == "qq_not_running":
        return "先启动并登录 QQ，再运行 key-diagnose。"
    return "先处理 LLDB/权限问题，再继续解密链路。"


__all__ = [
    "capture_passphrase",
    "diagnose_key_access",
    "find_qq_pid",
    "locate_nt_key_function_offset",
    "probe_lldb_attach",
]
