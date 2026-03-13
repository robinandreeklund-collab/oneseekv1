// Based on github.com/lightpanda-io/gomcp (Apache 2.0)
// Extended with additional browser automation tools for OneSeek integration.

package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"log/slog"
	"net/url"
	"regexp"
	"strings"

	md "github.com/JohannesKaufmann/html-to-markdown"
	"github.com/chromedp/cdproto/cdp"
	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/cdproto/runtime"
	"github.com/chromedp/chromedp"

	"github.com/robinandreeklund-collab/oneseekv1/lightpanda_mcp_server/mcp"
	"github.com/robinandreeklund-collab/oneseekv1/lightpanda_mcp_server/rpc"
)

// MCPConn manages a single client connection with a browser tab.
type MCPConn struct {
	srv       *MCPServer
	cdpctx    context.Context
	cdpcancel context.CancelFunc
}

func (c *MCPConn) Close() {
	if c.cdpcancel != nil {
		c.cdpcancel()
	}
}

func (c *MCPConn) connect() error {
	if c.cdpcancel != nil {
		c.cdpcancel()
	}

	var opts []chromedp.ContextOption
	if c.srv.Debug {
		opts = append(opts, chromedp.WithDebugf(log.Printf))
	}

	ctx, cancel := chromedp.NewContext(c.srv.cdpctx, opts...)

	if err := chromedp.Run(ctx); err != nil {
		cancel()
		return fmt.Errorf("new tab: %w", err)
	}

	c.cdpctx = ctx
	c.cdpcancel = cancel

	return nil
}

// Goto navigates to a URL and loads the page.
func (c *MCPConn) Goto(url string) (string, error) {
	if err := c.connect(); err != nil {
		return "", fmt.Errorf("browser connect: %w", err)
	}

	err := chromedp.Run(c.cdpctx, chromedp.Navigate(url))
	if err != nil {
		return "", fmt.Errorf("navigate %s: %w", url, err)
	}

	return fmt.Sprintf("The browser correctly navigated to '%s', the page is loaded in the context of the browser and can be used.", url), nil
}

// GetMarkdown returns the page content as markdown.
func (c *MCPConn) GetMarkdown() (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	var html string
	err := chromedp.Run(c.cdpctx, chromedp.OuterHTML("html", &html))
	if err != nil {
		return "", fmt.Errorf("outerHTML: %w", err)
	}

	converter := md.NewConverter("", true, nil)
	content, err := converter.ConvertString(html)
	if err != nil {
		return "", fmt.Errorf("convert to markdown: %w", err)
	}

	return content, nil
}

// GetLinks extracts all links from the current page.
func (c *MCPConn) GetLinks() ([]string, error) {
	if c.cdpctx == nil {
		return nil, errors.New("no browser connection, try to use goto first")
	}

	var a []*cdp.Node
	if err := chromedp.Run(c.cdpctx, chromedp.Nodes(`a[href]`, &a)); err != nil {
		return nil, fmt.Errorf("get links: %w", err)
	}

	links := make([]string, 0, len(a))
	for _, aa := range a {
		v, ok := aa.Attribute("href")
		if ok {
			links = append(links, v)
		}
	}

	return links, nil
}

// GetText extracts visible text content from a CSS selector.
func (c *MCPConn) GetText(selector string) (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	var text string
	err := chromedp.Run(c.cdpctx, chromedp.Text(selector, &text, chromedp.ByQuery))
	if err != nil {
		return "", fmt.Errorf("get text '%s': %w", selector, err)
	}

	return text, nil
}

// Screenshot captures the current page as a PNG image.
func (c *MCPConn) Screenshot(selector string, fullPage bool) (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	var buf []byte

	if selector != "" {
		// Screenshot a specific element
		err := chromedp.Run(c.cdpctx, chromedp.Screenshot(selector, &buf, chromedp.ByQuery))
		if err != nil {
			return "", fmt.Errorf("screenshot selector '%s': %w", selector, err)
		}
	} else if fullPage {
		// Full page screenshot
		err := chromedp.Run(c.cdpctx, chromedp.FullScreenshot(&buf, 90))
		if err != nil {
			return "", fmt.Errorf("full screenshot: %w", err)
		}
	} else {
		// Viewport screenshot
		err := chromedp.Run(c.cdpctx, chromedp.CaptureScreenshot(&buf))
		if err != nil {
			return "", fmt.Errorf("screenshot: %w", err)
		}
	}

	encoded := base64.StdEncoding.EncodeToString(buf)

	// Truncate if too large (>500KB base64)
	if len(encoded) > 500000 {
		return encoded[:500000] + "\n[TRUNCATED - image too large]", nil
	}

	return encoded, nil
}

// ExecuteJS runs JavaScript on the current page and returns the result.
func (c *MCPConn) ExecuteJS(script string) (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	var result *runtime.RemoteObject
	err := chromedp.Run(c.cdpctx, chromedp.Evaluate(script, &result))
	if err != nil {
		return "", fmt.Errorf("evaluate js: %w", err)
	}

	if result == nil {
		return "undefined", nil
	}

	// Try to extract the value
	var val interface{}
	if err := json.Unmarshal(result.Value, &val); err != nil {
		return string(result.Value), nil
	}

	b, _ := json.MarshalIndent(val, "", "  ")
	return string(b), nil
}

// Click clicks on an element matching the CSS selector.
func (c *MCPConn) Click(selector string) (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	err := chromedp.Run(c.cdpctx, chromedp.Click(selector, chromedp.ByQuery))
	if err != nil {
		return "", fmt.Errorf("click '%s': %w", selector, err)
	}

	return fmt.Sprintf("Clicked element matching '%s'.", selector), nil
}

// FillForm fills input fields and optionally submits a form.
func (c *MCPConn) FillForm(fields map[string]string, submitSelector string) (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	var actions []chromedp.Action
	for sel, val := range fields {
		actions = append(actions,
			chromedp.Clear(sel, chromedp.ByQuery),
			chromedp.SendKeys(sel, val, chromedp.ByQuery),
		)
	}

	if submitSelector != "" {
		actions = append(actions, chromedp.Click(submitSelector, chromedp.ByQuery))
	}

	err := chromedp.Run(c.cdpctx, actions...)
	if err != nil {
		return "", fmt.Errorf("fill form: %w", err)
	}

	filledCount := len(fields)
	msg := fmt.Sprintf("Filled %d field(s).", filledCount)
	if submitSelector != "" {
		msg += " Form submitted."
	}
	return msg, nil
}

// ExtractData extracts text from multiple CSS selectors.
func (c *MCPConn) ExtractData(selectors map[string]string) (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	results := make(map[string]string)
	for name, sel := range selectors {
		var text string
		err := chromedp.Run(c.cdpctx, chromedp.Text(sel, &text, chromedp.ByQuery))
		if err != nil {
			results[name] = fmt.Sprintf("[error: %s]", err.Error())
		} else {
			results[name] = strings.TrimSpace(text)
		}
	}

	b, _ := json.MarshalIndent(results, "", "  ")
	return string(b), nil
}

// FetchAPI navigates to a URL and extracts the raw text body (for JSON APIs).
func (c *MCPConn) FetchAPI(apiURL string, method string) (string, error) {
	if method == "" || strings.EqualFold(method, "GET") {
		// Simple GET — navigate to URL and extract body text
		if _, err := c.Goto(apiURL); err != nil {
			return "", err
		}

		var body string
		err := chromedp.Run(c.cdpctx, chromedp.Text("body", &body, chromedp.ByQuery))
		if err != nil {
			return "", fmt.Errorf("extract body: %w", err)
		}
		return strings.TrimSpace(body), nil
	}

	// For non-GET methods, use JavaScript fetch()
	script := fmt.Sprintf(`
		(async () => {
			const resp = await fetch(%q, { method: %q });
			const text = await resp.text();
			return JSON.stringify({
				status: resp.status,
				statusText: resp.statusText,
				headers: Object.fromEntries(resp.headers.entries()),
				body: text
			});
		})()
	`, apiURL, method)

	return c.ExecuteJS(script)
}

// GetFilteredLinks extracts links matching a regex pattern.
func (c *MCPConn) GetFilteredLinks(pattern string) ([]string, error) {
	allLinks, err := c.GetLinks()
	if err != nil {
		return nil, err
	}

	if pattern == "" {
		return allLinks, nil
	}

	re, err := regexp.Compile(pattern)
	if err != nil {
		return nil, fmt.Errorf("invalid regex pattern '%s': %w", pattern, err)
	}

	var filtered []string
	for _, link := range allLinks {
		if re.MatchString(link) {
			filtered = append(filtered, link)
		}
	}

	return filtered, nil
}

// SavePDF saves the current page as PDF and returns base64-encoded content.
func (c *MCPConn) SavePDF() (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	var buf []byte
	err := chromedp.Run(c.cdpctx, chromedp.ActionFunc(func(ctx context.Context) error {
		var err error
		buf, _, err = page.PrintToPDF().Do(ctx)
		return err
	}))
	if err != nil {
		return "", fmt.Errorf("print to pdf: %w", err)
	}

	encoded := base64.StdEncoding.EncodeToString(buf)

	if len(encoded) > 1000000 {
		return encoded[:1000000] + "\n[TRUNCATED - PDF too large]", nil
	}

	return encoded, nil
}

// WaitForSelector waits for a CSS selector to appear on the page.
func (c *MCPConn) WaitForSelector(selector string) (string, error) {
	if c.cdpctx == nil {
		return "", errors.New("no browser connection, try to use goto first")
	}

	err := chromedp.Run(c.cdpctx, chromedp.WaitVisible(selector, chromedp.ByQuery))
	if err != nil {
		return "", fmt.Errorf("wait for '%s': %w", selector, err)
	}

	return fmt.Sprintf("Element '%s' is now visible.", selector), nil
}

// ============================================================================
// MCP Server
// ============================================================================

type MCPServer struct {
	Name    string
	Version string
	Debug   bool

	cdpctx context.Context
}

func NewMCPServer(name, version string, cdpctx context.Context, debug bool) *MCPServer {
	return &MCPServer{
		Name:    name,
		Version: version,
		Debug:   debug,
		cdpctx:  cdpctx,
	}
}

func (s *MCPServer) NewConn() *MCPConn {
	return &MCPConn{
		srv: s,
	}
}

func (s *MCPServer) ListTools() []mcp.Tool {
	return []mcp.Tool{
		// ---- Original tools ----
		{
			Name: "goto",
			Description: "Navigate to a specified URL and load the page in memory " +
				"so it can be reused later for info extraction.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"url": mcp.NewSchemaString("The URL to navigate to, must be a valid URL."),
			}, []string{"url"}),
		},
		{
			Name:        "search",
			Description: "Use a search engine to look for specific words, terms, sentences. The search page will then be loaded in memory.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"text": mcp.NewSchemaString("The text to search for, must be a valid search query."),
			}, []string{"text"}),
		},
		{
			Name:        "markdown",
			Description: "Get the current page content in markdown format. Must call goto or search first.",
			InputSchema: mcp.NewSchemaObject(mcp.Properties{}),
		},
		{
			Name:        "links",
			Description: "Extract all hyperlinks from the current page. Optionally filter by regex pattern.",
			InputSchema: mcp.NewSchemaObject(mcp.Properties{
				"filter": mcp.NewSchemaString("Optional regex pattern to filter links (e.g. '.*\\.pdf$' for PDFs)."),
			}),
		},
		{
			Name:        "over",
			Description: "Signal that the task is complete and provide the final answer. This should be the last tool called.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"result": mcp.NewSchemaString("The final result of the task."),
			}, []string{"result"}),
		},

		// ---- Extended tools ----
		{
			Name:        "get_text",
			Description: "Extract the visible text content from a specific element using a CSS selector. Must call goto first.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"selector": mcp.NewSchemaString("CSS selector for the element (e.g. 'h1', '.main-content', '#article-body')."),
			}, []string{"selector"}),
		},
		{
			Name:        "click",
			Description: "Click on an element matching a CSS selector. Useful for buttons, links, dropdowns, tabs. Must call goto first.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"selector": mcp.NewSchemaString("CSS selector for the element to click (e.g. 'button.submit', '#login-btn')."),
			}, []string{"selector"}),
		},
		{
			Name:        "screenshot",
			Description: "Take a screenshot of the current page or a specific element. Returns base64-encoded PNG. Must call goto first.",
			InputSchema: mcp.NewSchemaObject(mcp.Properties{
				"selector":  mcp.NewSchemaString("Optional CSS selector to screenshot a specific element."),
				"full_page": mcp.NewSchemaBoolean("If true, capture the full scrollable page. Default false."),
			}),
		},
		{
			Name:        "execute_js",
			Description: "Execute JavaScript code on the current page and return the result. Must call goto first. Use for complex DOM queries, computing values, or interacting with page APIs.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"script": mcp.NewSchemaString("JavaScript code to execute. The return value will be serialized to JSON."),
			}, []string{"script"}),
		},
		{
			Name: "fill_form",
			Description: "Fill form fields and optionally submit the form. Must call goto first. " +
				"The 'fields' parameter maps CSS selectors to values.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"fields":          mcp.NewSchemaObjectField("Map of CSS selectors to values, e.g. {\"#email\": \"user@example.com\", \"#password\": \"secret\"}."),
				"submit_selector": mcp.NewSchemaString("Optional CSS selector for the submit button to click after filling fields."),
			}, []string{"fields"}),
		},
		{
			Name: "extract_data",
			Description: "Extract text from multiple CSS selectors at once. Returns a JSON object mapping " +
				"names to extracted text. Must call goto first.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"selectors": mcp.NewSchemaObjectField("Map of names to CSS selectors, e.g. {\"title\": \"h1\", \"price\": \".price-tag\", \"description\": \".product-desc\"}."),
			}, []string{"selectors"}),
		},
		{
			Name:        "fetch_api",
			Description: "Fetch data from a URL (typically a REST API returning JSON). Navigates to the URL and extracts the raw response body.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"url":    mcp.NewSchemaString("The API endpoint URL to fetch."),
				"method": mcp.NewSchemaEnum("HTTP method. Default: GET.", []string{"GET", "POST", "PUT", "DELETE"}),
			}, []string{"url"}),
		},
		{
			Name:        "save_pdf",
			Description: "Save the current page as a PDF document. Returns base64-encoded PDF content. Must call goto first.",
			InputSchema: mcp.NewSchemaObject(mcp.Properties{}),
		},
		{
			Name:        "wait_for",
			Description: "Wait for an element matching a CSS selector to become visible on the page. Useful for pages with dynamic content loading. Must call goto first.",
			InputSchema: mcp.NewSchemaObjectRequired(mcp.Properties{
				"selector": mcp.NewSchemaString("CSS selector to wait for (e.g. '.results-loaded', '#content')."),
			}, []string{"selector"}),
		},
	}
}

var ErrNoTool = errors.New("no tool found")

func (s *MCPServer) CallTool(ctx context.Context, conn *MCPConn, req mcp.ToolsCallRequest) (string, error) {
	v := req.Params.Arguments

	switch req.Params.Name {
	case "goto":
		var args struct {
			URL string `json:"url"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if args.URL == "" {
			return "", errors.New("no url")
		}
		return conn.Goto(args.URL)

	case "search":
		var args struct {
			Text string `json:"text"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if args.Text == "" {
			return "", errors.New("no text")
		}
		urlString := "https://duckduckgo.com/?q=" + url.QueryEscape(args.Text)
		return conn.Goto(urlString)

	case "markdown":
		return conn.GetMarkdown()

	case "links":
		var args struct {
			Filter string `json:"filter"`
		}
		// Silently ignore parse error for empty args
		json.Unmarshal(v, &args)

		links, err := conn.GetFilteredLinks(args.Filter)
		if err != nil {
			return "", err
		}
		return strings.Join(links, "\n"), nil

	case "over":
		var args struct {
			Text string `json:"result"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		return args.Text, nil

	// ---- Extended tools ----

	case "get_text":
		var args struct {
			Selector string `json:"selector"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if args.Selector == "" {
			return "", errors.New("no selector")
		}
		return conn.GetText(args.Selector)

	case "click":
		var args struct {
			Selector string `json:"selector"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if args.Selector == "" {
			return "", errors.New("no selector")
		}
		return conn.Click(args.Selector)

	case "screenshot":
		var args struct {
			Selector string `json:"selector"`
			FullPage bool   `json:"full_page"`
		}
		json.Unmarshal(v, &args)
		return conn.Screenshot(args.Selector, args.FullPage)

	case "execute_js":
		var args struct {
			Script string `json:"script"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if args.Script == "" {
			return "", errors.New("no script")
		}
		return conn.ExecuteJS(args.Script)

	case "fill_form":
		var args struct {
			Fields         map[string]string `json:"fields"`
			SubmitSelector string            `json:"submit_selector"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if len(args.Fields) == 0 {
			return "", errors.New("no fields")
		}
		return conn.FillForm(args.Fields, args.SubmitSelector)

	case "extract_data":
		var args struct {
			Selectors map[string]string `json:"selectors"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if len(args.Selectors) == 0 {
			return "", errors.New("no selectors")
		}
		return conn.ExtractData(args.Selectors)

	case "fetch_api":
		var args struct {
			URL    string `json:"url"`
			Method string `json:"method"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if args.URL == "" {
			return "", errors.New("no url")
		}
		return conn.FetchAPI(args.URL, args.Method)

	case "save_pdf":
		return conn.SavePDF()

	case "wait_for":
		var args struct {
			Selector string `json:"selector"`
		}
		if err := json.Unmarshal(v, &args); err != nil {
			return "", fmt.Errorf("args decode: %w", err)
		}
		if args.Selector == "" {
			return "", errors.New("no selector")
		}
		return conn.WaitForSelector(args.Selector)
	}

	return "", ErrNoTool
}

var ErrRPCRequest = errors.New("rpc request error")

func (s *MCPServer) Decode(in io.Reader) (mcp.Request, error) {
	var empty mcp.Request

	dec := json.NewDecoder(in)
	var rreq rpc.Request
	if err := dec.Decode(&rreq); err != nil {
		return empty, fmt.Errorf("json decode: %w", err)
	}

	if err := rreq.Validate(); err != nil {
		return empty, fmt.Errorf("rpc validate: %w", err)
	}

	if err := rreq.Err(); err != nil {
		return empty, errors.Join(ErrRPCRequest, rreq.Err())
	}

	mcpreq, err := mcp.Decode(rreq)
	if err != nil {
		return empty, fmt.Errorf("mcp validate: %w", err)
	}

	return mcpreq, err
}

type SendFn func(string, any) error

func (s *MCPServer) Handle(
	ctx context.Context,
	rreq mcp.Request,
	mcpconn *MCPConn,
	send SendFn,
) error {
	var senderr error
	switch r := rreq.(type) {
	case mcp.InitializeRequest:
		senderr = send("message", rpc.NewResponse(mcp.InitializeResponse{
			ProtocolVersion: mcp.Version,
			ServerInfo: mcp.Info{
				Name:    s.Name,
				Version: s.Version,
			},
			Capabilities: mcp.Capabilities{"tools": mcp.Capability{}},
		}, r.Request.Id))
	case mcp.PromptsListRequest:
		senderr = send("message", rpc.NewResponse(struct{}{}, r.Id))
	case mcp.ResourcesListRequest:
		senderr = send("message", rpc.NewResponse(struct{}{}, r.Id))
	case mcp.ToolsListRequest:
		senderr = send("message", rpc.NewResponse(mcp.ToolsListResponse{
			Tools: s.ListTools(),
		}, r.Id))
	case mcp.ToolsCallRequest:
		slog.Debug("call tool", slog.String("name", r.Params.Name), slog.Int("id", r.Id))
		go func() {
			res, err := s.CallTool(ctx, mcpconn, r)

			if err != nil {
				slog.Error("call tool", slog.String("name", r.Params.Name), slog.Any("err", err))
				send("message", rpc.NewResponse(mcp.ToolsCallResponse{
					IsError: true,
					Content: []mcp.ToolsCallContent{{
						Type: "text",
						Text: err.Error(),
					}},
				}, r.Id))
				return
			}

			send("message", rpc.NewResponse(mcp.ToolsCallResponse{
				Content: []mcp.ToolsCallContent{{
					Type: "text",
					Text: res,
				}},
			}, r.Id))
		}()

	case mcp.NotificationsCancelledRequest:
		slog.Debug("cancelled",
			slog.Int("id", r.Params.RequestId),
			slog.String("reason", r.Params.Reason),
		)
	}

	if senderr != nil {
		return fmt.Errorf("send message: %w", senderr)
	}

	return nil
}
