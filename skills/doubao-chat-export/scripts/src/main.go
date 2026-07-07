// Command doubao-export is a cross-platform, zero-runtime-dependency single
// binary that exports Doubao (doubao.com) desktop chat history via the locally
// logged-in session. No browser, no a_bogus/msToken signature: the only
// credential is the cookie jar decrypted from the installed Doubao desktop app.
//
// Subcommands:
//
//	doubao-export list                     # list conversations           -> JSON (stdout)
//	doubao-export pull <conversation_id>   # one conversation's messages   -> JSON (stdout)
//	doubao-export export [outDir]          # list + pull every conversation -> JSON files
//
// Reads the local Chromium SQLite cookie DB with the pure-Go modernc.org/sqlite
// driver (no sqlite3 CLI), decrypts cookies with a per-platform implementation
// (see cookies_<os>.go), and calls Doubao's own backend API.
//
// Output JSON goes to stdout; logs / progress go to stderr.
package main

import (
	"bytes"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	host      = "https://www.doubao.com"
	listPath  = "/samantha/thread/list"
	chainPath = "/im/chain/single"

	userAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) " +
		"Doubao/2.13.8 Chrome/135.0.7049.72 Electron Safari/537.36"

	// IMCMD / enums (from the desktop bundle launcher2_page chunk).
	cmdPullSingleChain = 3100
	convTypeOneToBot   = 3 // ConversationType.ONE_TO_BOT_CHAT
	dirOlder           = 1 // MessageDirection.OLDER
	dirNewer           = 2 // MessageDirection.NEWER
	dirFromLatest      = 3 // MessageDirection.FROM_LATEST
	userTypeHuman      = 1
	userTypeAIBot      = 2
	userTypeSystem     = 3

	exportInterval = 400 * time.Millisecond

	maxPullPages = 500 // safety cap on pagination (full + incremental)
)

// ---------------------------------------------------------------------------
// request / response shapes
// ---------------------------------------------------------------------------

type envelope struct {
	Cmd        int        `json:"cmd"`
	SequenceID string     `json:"sequence_id"`
	Channel    int        `json:"channel"`
	Version    string     `json:"version"`
	UplinkBody uplinkBody `json:"uplink_body"`
}

type uplinkBody struct {
	// NOTE: spelling is intentionally "singe" (matches the wire field name).
	PullSingeChain pullSingeChainUplink `json:"pull_singe_chain_uplink_body"`
}

type pullSingeChainUplink struct {
	ConversationID   string `json:"conversation_id"`
	AnchorIndex      int64  `json:"anchor_index"`
	ConversationType int    `json:"conversation_type"`
	Direction        int    `json:"direction"`
	Limit            int    `json:"limit"`
	// IMPORTANT: do NOT send "filter" or "ext". Including filter{index_list,bot_id}
	// triggers a server-side 712010702 系统内部异常. Omit them entirely.
}

type chainResp struct {
	Cmd          int    `json:"cmd"`
	StatusCode   int    `json:"status_code"`
	StatusDesc   string `json:"status_desc"`
	DownlinkBody struct {
		Pull struct {
			Messages []rawMessage `json:"messages"`
			HasMore  bool         `json:"has_more"`
		} `json:"pull_singe_chain_downlink_body"`
	} `json:"downlink_body"`
}

type rawMessage struct {
	ConversationID string         `json:"conversation_id"`
	MessageID      string         `json:"message_id"`
	UserType       int            `json:"user_type"` // 1=human 2=bot 3=system
	ContentType    int            `json:"content_type"`
	Content        string         `json:"content"`
	IndexInConv    string         `json:"index_in_conv"`
	CreateTime     string         `json:"create_time"`
	Brief          string         `json:"brief"`
	TTSContent     string         `json:"tts_content"`
	ContentBlock   []contentBlock `json:"content_block"`
}

type contentBlock struct {
	Content struct {
		TextBlock struct {
			Text string `json:"text"`
		} `json:"text_block"`
	} `json:"content"`
}

func (m rawMessage) text() string {
	var s string
	for _, b := range m.ContentBlock {
		s += b.Content.TextBlock.Text
	}
	if s != "" {
		return s
	}
	if m.Content != "" {
		return unwrapContent(m.Content)
	}
	if m.Brief != "" {
		return m.Brief
	}
	return m.TTSContent
}

// unwrapContent handles messages (often the user side) whose content is a JSON
// envelope like {"text":"..."} rather than plain text; returns the inner text.
func unwrapContent(s string) string {
	if len(s) > 0 && s[0] == '{' {
		var v struct {
			Text string `json:"text"`
		}
		if err := json.Unmarshal([]byte(s), &v); err == nil && v.Text != "" {
			return v.Text
		}
	}
	return s
}

func (m rawMessage) role() string {
	switch m.UserType {
	case userTypeHuman:
		return "user"
	case userTypeAIBot:
		return "assistant"
	case userTypeSystem:
		return "system"
	default:
		return "unknown"
	}
}

// Conversation is the normalized list-item output.
type Conversation struct {
	ConversationID   string      `json:"conversation_id"`
	Name             string      `json:"name"`
	BotID            string      `json:"bot_id"`
	ConversationType int         `json:"conversation_type"`
	MessageIndex     json.Number `json:"message_index"`
}

// Message is the normalized message output.
type Message struct {
	MessageID      string `json:"message_id"`
	ConversationID string `json:"conversation_id"`
	Role           string `json:"role"`
	Text           string `json:"text"`
	ContentType    int    `json:"content_type"`
	IndexInConv    string `json:"index_in_conv"`
	CreateTime     string `json:"create_time"`
}

// thread/list response (plain JSON).
type listResp struct {
	Code int    `json:"code"`
	Msg  string `json:"msg"`
	Data struct {
		ThreadList []struct {
			Conversation struct {
				ConversationID   string      `json:"conversation_id"`
				Name             string      `json:"name"`
				BotID            string      `json:"bot_id"`
				ConversationType int         `json:"conversation_type"`
				MessageIndex     json.Number `json:"message_index"`
			} `json:"conversation"`
		} `json:"thread_list"`
		HasMore    bool   `json:"has_more"`
		NextCursor string `json:"next_cursor"`
		Cursor     string `json:"cursor"`
	} `json:"data"`
}

// ---------------------------------------------------------------------------
// client
// ---------------------------------------------------------------------------

type client struct {
	cookie string
	qs     string
	http   *http.Client
}

func newClient() (*client, error) {
	dir, err := dataDir()
	if err != nil {
		return nil, err
	}
	logf("豆包数据目录: %s", dir)

	jar, err := cookieJar(dir)
	if err != nil {
		return nil, err
	}
	if jar["sessionid"] == "" && jar["sid_guard"] == "" {
		return nil, fmt.Errorf("未在豆包 cookie 里找到登录态(sessionid/sid_guard)。请先在豆包桌面版登录。")
	}
	logf("已解密 %d 个 cookie", len(jar))

	cookie := joinCookies(jar)
	qs := queryParams(dir)
	logf("query 参数: %.80s...", qs)

	return &client{cookie: cookie, qs: qs, http: &http.Client{Timeout: 30 * time.Second}}, nil
}

func joinCookies(jar map[string]string) string {
	var b bytes.Buffer
	first := true
	for k, v := range jar {
		if v == "" {
			continue
		}
		if !first {
			b.WriteString("; ")
		}
		b.WriteString(k)
		b.WriteByte('=')
		b.WriteString(v)
		first = false
	}
	return b.String()
}

func (c *client) post(apiPath string, body any, out any) (int, error) {
	raw, _ := json.Marshal(body)
	req, err := http.NewRequest("POST", host+apiPath+"?"+c.qs, bytes.NewReader(raw))
	if err != nil {
		return 0, err
	}
	req.Header.Set("Cookie", c.cookie)
	req.Header.Set("User-Agent", userAgent)
	req.Header.Set("Origin", host)
	req.Header.Set("Referer", host+"/")
	// The two headers that make the AGW gateway do JSON<->protobuf conversion:
	req.Header.Set("Agw-Js-Conv", "str")
	req.Header.Set("Content-Type", "application/json; encoding=utf-8")

	resp, err := c.http.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if err := json.Unmarshal(data, out); err != nil {
		return resp.StatusCode, fmt.Errorf("非 JSON 响应 (HTTP %d): %.200s", resp.StatusCode, data)
	}
	return resp.StatusCode, nil
}

func uuid() string {
	var b [16]byte
	rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func (c *client) listConversations() ([]Conversation, error) {
	var out []Conversation
	seen := map[string]bool{}
	cursor := ""
	for page := 0; page < 200; page++ {
		var lr listResp
		_, err := c.post(listPath, map[string]any{"count": 30, "cursor": cursor}, &lr)
		if err != nil {
			return out, err
		}
		if lr.Code != 0 {
			return out, fmt.Errorf("thread/list code=%d msg=%s", lr.Code, lr.Msg)
		}
		items := lr.Data.ThreadList
		for _, it := range items {
			c := it.Conversation
			if c.ConversationID == "" || seen[c.ConversationID] {
				continue
			}
			seen[c.ConversationID] = true
			out = append(out, Conversation{
				ConversationID:   c.ConversationID,
				Name:             c.Name,
				BotID:            c.BotID,
				ConversationType: c.ConversationType,
				MessageIndex:     c.MessageIndex,
			})
		}
		cursor = lr.Data.NextCursor
		if cursor == "" {
			cursor = lr.Data.Cursor
		}
		if !lr.Data.HasMore || len(items) == 0 || cursor == "" {
			break
		}
	}
	return out, nil
}

func (c *client) pullHistory(convID string) ([]Message, error) {
	var all []rawMessage
	seen := map[string]bool{}
	anchor := int64(0)
	dir := dirFromLatest
	for page := 0; page < maxPullPages; page++ {
		env := envelope{
			Cmd:        cmdPullSingleChain,
			SequenceID: uuid(),
			Channel:    2,
			Version:    "1",
			UplinkBody: uplinkBody{PullSingeChain: pullSingeChainUplink{
				ConversationID:   convID,
				AnchorIndex:      anchor,
				ConversationType: convTypeOneToBot,
				Direction:        dir,
				Limit:            50,
			}},
		}
		var cr chainResp
		_, err := c.post(chainPath, env, &cr)
		if err != nil {
			return toMessages(all), err
		}
		if cr.StatusCode != 0 {
			return toMessages(all), fmt.Errorf("im/chain/single status_code=%d desc=%s", cr.StatusCode, cr.StatusDesc)
		}
		msgs := cr.DownlinkBody.Pull.Messages
		if len(msgs) == 0 {
			break
		}
		minIdx := int64(1<<62 - 1)
		for _, m := range msgs {
			if !seen[m.MessageID] {
				seen[m.MessageID] = true
				all = append(all, m)
			}
			if v, e := strconv.ParseInt(m.IndexInConv, 10, 64); e == nil && v < minIdx {
				minIdx = v
			}
		}
		if !cr.DownlinkBody.Pull.HasMore {
			break
		}
		anchor = minIdx
		dir = dirOlder
	}
	sort.SliceStable(all, func(i, j int) bool {
		a, _ := strconv.ParseInt(all[i].IndexInConv, 10, 64)
		b, _ := strconv.ParseInt(all[j].IndexInConv, 10, 64)
		return a < b
	})
	return toMessages(all), nil
}

func toMessages(raw []rawMessage) []Message {
	out := make([]Message, 0, len(raw))
	for _, m := range raw {
		out = append(out, Message{
			MessageID:      m.MessageID,
			ConversationID: m.ConversationID,
			Role:           m.role(),
			Text:           m.text(),
			ContentType:    m.ContentType,
			IndexInConv:    m.IndexInConv,
			CreateTime:     m.CreateTime,
		})
	}
	return out
}

// ---------------------------------------------------------------------------
// local cache + incremental pull
// ---------------------------------------------------------------------------

// convCache is the on-disk per-conversation cache. Messages are already
// message_id-deduped and sorted ascending by index_in_conv. MaxIndex is the
// largest index_in_conv seen so far, used as the NEWER anchor on next run.
type convCache struct {
	MaxIndex int64     `json:"max_index"`
	Messages []Message `json:"messages"`
}

// cacheDir returns the directory that holds per-conversation cache files,
// creating it if needed. Falls back to os.TempDir() when UserCacheDir fails.
func cacheDir() string {
	base, err := os.UserCacheDir()
	if err != nil || base == "" {
		base = os.TempDir()
	}
	dir := filepath.Join(base, "doubao-export")
	_ = os.MkdirAll(dir, 0o755)
	return dir
}

func cachePath(convID string) string {
	return filepath.Join(cacheDir(), convID+".json")
}

// readCache loads the cache file for convID. A missing/unreadable/corrupt file
// is treated as an empty cache (returns ok=false, no error).
func readCache(convID string) (convCache, bool) {
	data, err := os.ReadFile(cachePath(convID))
	if err != nil {
		return convCache{}, false
	}
	var c convCache
	if err := json.Unmarshal(data, &c); err != nil {
		return convCache{}, false
	}
	return c, true
}

func writeCache(convID string, c convCache) error {
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(cachePath(convID), data, 0o644)
}

func parseIdx(s string) int64 {
	v, _ := strconv.ParseInt(s, 10, 64)
	return v
}

// pullNewer pages forward (NEWER direction) from anchor (an index_in_conv),
// returning only messages strictly newer than anchor. It advances the anchor to
// the max index seen each page, stops on has_more=false or when no page yields a
// larger index, and is bounded by maxPullPages to avoid runaway loops.
func (c *client) pullNewer(convID string, anchor int64) ([]rawMessage, error) {
	var all []rawMessage
	seen := map[string]bool{}
	for page := 0; page < maxPullPages; page++ {
		env := envelope{
			Cmd:        cmdPullSingleChain,
			SequenceID: uuid(),
			Channel:    2,
			Version:    "1",
			UplinkBody: uplinkBody{PullSingeChain: pullSingeChainUplink{
				ConversationID:   convID,
				AnchorIndex:      anchor,
				ConversationType: convTypeOneToBot,
				Direction:        dirNewer,
				Limit:            50,
			}},
		}
		var cr chainResp
		_, err := c.post(chainPath, env, &cr)
		if err != nil {
			return all, err
		}
		if cr.StatusCode != 0 {
			return all, fmt.Errorf("im/chain/single status_code=%d desc=%s", cr.StatusCode, cr.StatusDesc)
		}
		msgs := cr.DownlinkBody.Pull.Messages
		if len(msgs) == 0 {
			break
		}
		maxIdx := anchor
		for _, m := range msgs {
			idx := parseIdx(m.IndexInConv)
			// Only keep messages strictly newer than the anchor we started from.
			if idx > anchor && !seen[m.MessageID] {
				seen[m.MessageID] = true
				all = append(all, m)
			}
			if idx > maxIdx {
				maxIdx = idx
			}
		}
		if !cr.DownlinkBody.Pull.HasMore {
			break
		}
		// Termination guard: if the page produced nothing newer than the anchor,
		// advancing would loop forever — stop.
		if maxIdx <= anchor {
			break
		}
		anchor = maxIdx
	}
	return all, nil
}

// pullHistoryCached returns the full message list for convID, using a local
// cache and an incremental NEWER fetch when a cache exists. With no cache it
// falls back to the full pullHistory. The cache is updated and written back on
// success. Returns the merged, deduped, index-ascending full message list.
func (c *client) pullHistoryCached(convID string) ([]Message, error) {
	cache, ok := readCache(convID)
	if !ok {
		// First time: full pull.
		msgs, err := c.pullHistory(convID)
		if err != nil {
			return msgs, err
		}
		max := int64(0)
		for _, m := range msgs {
			if idx := parseIdx(m.IndexInConv); idx > max {
				max = idx
			}
		}
		_ = writeCache(convID, convCache{MaxIndex: max, Messages: msgs})
		logf("  [缓存] %s 首次全量, %d 条", convID, len(msgs))
		return msgs, nil
	}

	// Have cache: pull only messages newer than the cached anchor.
	rawNew, err := c.pullNewer(convID, cache.MaxIndex)
	if err != nil {
		// On error, still return what we have cached so search isn't broken.
		logf("  [缓存] %s 增量拉取出错, 用缓存(%d 条): %v", convID, len(cache.Messages), err)
		return cache.Messages, err
	}
	newMsgs := toMessages(rawNew)

	if len(newMsgs) == 0 {
		logf("  [缓存] %s 命中缓存, 新增 0 条 (共 %d 条)", convID, len(cache.Messages))
		return cache.Messages, nil
	}

	// Merge cached + new, dedupe by message_id, sort ascending by index.
	merged := make([]Message, 0, len(cache.Messages)+len(newMsgs))
	merged = append(merged, cache.Messages...)
	seen := make(map[string]bool, len(merged))
	for _, m := range merged {
		seen[m.MessageID] = true
	}
	for _, m := range newMsgs {
		if !seen[m.MessageID] {
			seen[m.MessageID] = true
			merged = append(merged, m)
		}
	}
	sort.SliceStable(merged, func(i, j int) bool {
		return parseIdx(merged[i].IndexInConv) < parseIdx(merged[j].IndexInConv)
	})

	max := cache.MaxIndex
	for _, m := range merged {
		if idx := parseIdx(m.IndexInConv); idx > max {
			max = idx
		}
	}
	_ = writeCache(convID, convCache{MaxIndex: max, Messages: merged})
	logf("  [缓存] %s 命中缓存, 增量新增 %d 条 (共 %d 条)", convID, len(newMsgs), len(merged))
	return merged, nil
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

func logf(format string, a ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", a...)
}

func printJSON(v any) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		fatal("编码 JSON 失败: %v", err)
	}
}

func fatal(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "错误: "+format+"\n", a...)
	os.Exit(1)
}

func usage() {
	fmt.Fprint(os.Stderr, `用法:
  doubao-export list                     列出会话 (JSON -> stdout)
  doubao-export pull <conversation_id>   导出单个会话消息 (JSON -> stdout)
  doubao-export export [outDir]          导出全部会话到 JSON 文件 (默认 ./doubao-export-out)
  doubao-export search <关键词> [conv_id] 在全部(或指定)会话正文里搜关键词 (JSON -> stdout)
`)
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}
	cmd := os.Args[1]

	switch cmd {
	case "list":
		c, err := newClient()
		if err != nil {
			fatal("%v", err)
		}
		convs, err := c.listConversations()
		if err != nil {
			fatal("%v", err)
		}
		logf("共 %d 个会话", len(convs))
		printJSON(convs)

	case "pull":
		if len(os.Args) < 3 {
			fatal("用法: doubao-export pull <conversation_id>")
		}
		c, err := newClient()
		if err != nil {
			fatal("%v", err)
		}
		msgs, err := c.pullHistory(os.Args[2])
		if err != nil {
			// Still print whatever we got, then exit non-zero.
			logf("拉取过程中出错: %v", err)
			printJSON(msgs)
			os.Exit(1)
		}
		logf("共 %d 条消息", len(msgs))
		printJSON(msgs)

	case "export":
		outDir := "doubao-export-out"
		if len(os.Args) >= 3 {
			outDir = os.Args[2]
		}
		c, err := newClient()
		if err != nil {
			fatal("%v", err)
		}
		runExport(c, outDir)

	case "search":
		if len(os.Args) < 3 {
			fatal("用法: doubao-export search <关键词> [conversation_id]")
		}
		c, err := newClient()
		if err != nil {
			fatal("%v", err)
		}
		convID := ""
		if len(os.Args) >= 4 {
			convID = os.Args[3]
		}
		runSearch(c, os.Args[2], convID)

	case "-h", "--help", "help":
		usage()

	default:
		fatal("未知子命令 %q", cmd)
	}
}

// SearchMatch is one message that matched a search keyword.
type SearchMatch struct {
	ConversationID   string `json:"conversation_id"`
	ConversationName string `json:"conversation_name"`
	Role             string `json:"role"`
	Snippet          string `json:"snippet"`
	Text             string `json:"text"`
	CreateTime       string `json:"create_time"`
	IndexInConv      string `json:"index_in_conv"`
}

// runSearch searches message text for kw across all conversations (or just one
// if convID is given) and prints matches as JSON. Content lives server-side, so
// this pulls each conversation's history and matches locally.
func runSearch(c *client, kw, convID string) {
	var targets []Conversation
	if convID != "" {
		targets = []Conversation{{ConversationID: convID, Name: convID}}
	} else {
		convs, err := c.listConversations()
		if err != nil {
			fatal("%v", err)
		}
		targets = convs
	}
	logf("在 %d 个会话里搜索 %q ...", len(targets), kw)

	matches := []SearchMatch{}
	for i, cv := range targets {
		msgs, err := c.pullHistoryCached(cv.ConversationID)
		if err != nil {
			logf("  ! [%d/%d] %s (%s): %v", i+1, len(targets), cv.Name, cv.ConversationID, err)
			if convID == "" {
				time.Sleep(exportInterval)
			}
			continue
		}
		n := 0
		for _, m := range msgs {
			if strings.Contains(m.Text, kw) {
				matches = append(matches, SearchMatch{
					ConversationID:   cv.ConversationID,
					ConversationName: cv.Name,
					Role:             m.Role,
					Snippet:          snippet(m.Text, kw),
					Text:             m.Text,
					CreateTime:       m.CreateTime,
					IndexInConv:      m.IndexInConv,
				})
				n++
			}
		}
		if n > 0 {
			logf("  [%d/%d] %s: %d 处命中", i+1, len(targets), cv.Name, n)
		}
		if convID == "" {
			time.Sleep(exportInterval)
		}
	}
	logf("共 %d 处命中", len(matches))
	printJSON(matches)
}

// snippet returns a short rune-safe window around the first occurrence of kw.
func snippet(text, kw string) string {
	i := strings.Index(text, kw)
	if i < 0 {
		return strings.ReplaceAll(text, "\n", " ")
	}
	runes := []rune(text)
	pre := len([]rune(text[:i]))
	klen := len([]rune(kw))
	start := pre - 15
	if start < 0 {
		start = 0
	}
	end := pre + klen + 35
	if end > len(runes) {
		end = len(runes)
	}
	return strings.ReplaceAll(string(runes[start:end]), "\n", " ")
}

func runExport(c *client, outDir string) {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		fatal("创建输出目录失败: %v", err)
	}
	convs, err := c.listConversations()
	if err != nil {
		fatal("%v", err)
	}
	logf("共 %d 个会话, 开始导出 -> %s", len(convs), outDir)

	convData, _ := json.MarshalIndent(convs, "", "  ")
	if err := os.WriteFile(filepath.Join(outDir, "conversations.json"), convData, 0o644); err != nil {
		fatal("写 conversations.json 失败: %v", err)
	}

	ok := 0
	for i, cv := range convs {
		msgs, err := c.pullHistory(cv.ConversationID)
		if err != nil {
			logf("  ! [%d/%d] %s (%s): %v", i+1, len(convs), cv.Name, cv.ConversationID, err)
			time.Sleep(exportInterval)
			continue
		}
		out := struct {
			Conversation
			Messages []Message `json:"messages"`
		}{Conversation: cv, Messages: msgs}
		data, _ := json.MarshalIndent(out, "", "  ")
		fp := filepath.Join(outDir, cv.ConversationID+".json")
		if err := os.WriteFile(fp, data, 0o644); err != nil {
			logf("  ! [%d/%d] 写 %s 失败: %v", i+1, len(convs), fp, err)
		} else {
			ok++
			logf("  [%d/%d] %s (%d 条消息)", i+1, len(convs), cv.Name, len(msgs))
		}
		time.Sleep(exportInterval)
	}
	logf("导出完成: %d/%d 个会话 -> %s", ok, len(convs), outDir)
	printJSON(map[string]any{"exported": ok, "total": len(convs), "outDir": outDir})
}
