// Based on github.com/lightpanda-io/gomcp (Apache 2.0)
// Extended with additional browser automation tools for OneSeek.

package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/chromedp/chromedp"
)

const (
	exitOK   = 0
	exitFail = 1
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()

	err := run(ctx, os.Args, os.Stdin, os.Stdout, os.Stderr)
	if err != nil {
		fmt.Fprintln(os.Stderr, err.Error())
		os.Exit(exitFail)
	}

	os.Exit(exitOK)
}

const (
	ApiDefaultAddress = "127.0.0.1:8081"
)

func run(ctx context.Context, args []string, stdin io.Reader, stdout, stderr io.Writer) error {
	flags := flag.NewFlagSet(args[0], flag.ExitOnError)
	flags.SetOutput(stderr)

	var (
		verbose = flags.Bool("verbose", false, "enable debug log level")
		apiaddr = flags.String("api-addr", env("MCP_API_ADDRESS", ApiDefaultAddress), "http api server address")
		cdp     = flags.String("cdp", os.Getenv("MCP_CDP"), "cdp ws to connect. By default gomcp will run the downloaded Lightpanda browser.")
	)

	exec := args[0]
	flags.Usage = func() {
		fmt.Fprintf(stderr, "usage: %s sse|stdio|download|cleanup\n", exec)
		fmt.Fprintf(stderr, "OneSeek Lightpanda MCP server — extended browser automation.\n")
		fmt.Fprintf(stderr, "\nCommands:\n")
		fmt.Fprintf(stderr, "\tstdio\t\tstarts the stdio server\n")
		fmt.Fprintf(stderr, "\tsse\t\tstarts the HTTP SSE MCP server\n")
		fmt.Fprintf(stderr, "\tdownload\tinstalls or updates the Lightpanda browser\n")
		fmt.Fprintf(stderr, "\tcleanup\t\tremoves the Lightpanda browser\n")
		fmt.Fprintf(stderr, "\nCommand line options:\n")
		flags.PrintDefaults()
		fmt.Fprintf(stderr, "\nEnvironment vars:\n")
		fmt.Fprintf(stderr, "\tMCP_API_ADDRESS\t\tdefault %s\n", ApiDefaultAddress)
		fmt.Fprintf(stderr, "\tMCP_CDP\t\t\tWebSocket URL to Lightpanda CDP\n")
	}
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}

	args = flags.Args()
	if len(args) != 1 {
		flags.Usage()
		return errors.New("bad arguments")
	}

	if *verbose {
		slog.SetLogLoggerLevel(slog.LevelDebug)
	}

	// Commands without browser
	switch args[0] {
	case "cleanup":
		return cleanup(ctx)
	case "download":
		return download(ctx)
	}

	// Commands with browser
	cdpws := "ws://127.0.0.1:9222"
	if *cdp == "" {
		// Start the local browser
		ctx, cancel := context.WithCancel(ctx)
		defer cancel()

		browser, err := newbrowser(ctx)
		if err != nil {
			if errors.Is(err, ErrNoBrowser) {
				return errors.New("browser not found. Please run gomcp download first.")
			}
			return fmt.Errorf("new browser: %w", err)
		}

		done := make(chan struct{})
		defer func() {
			<-done
		}()

		go func() {
			if err := browser.Run(); err != nil {
				slog.Error("run browser", slog.Any("err", err))
			}
			close(done)
		}()

		defer cancel()
	} else {
		cdpws = *cdp
	}

	cdpctx, cancel := chromedp.NewRemoteAllocator(ctx,
		cdpws, chromedp.NoModifyURL,
	)
	defer cancel()

	mcpsrv := NewMCPServer("oneseek-lightpanda-mcp", "1.0.0", cdpctx, *verbose)

	switch args[0] {
	case "stdio":
		return runstd(ctx, stdin, stdout, mcpsrv)
	case "sse":
		return runapi(ctx, *apiaddr, mcpsrv)
	}

	flags.Usage()
	return errors.New("bad command")
}

func env(key, dflt string) string {
	val, ok := os.LookupEnv(key)
	if !ok {
		return dflt
	}
	return val
}
