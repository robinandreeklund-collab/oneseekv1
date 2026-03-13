// Based on github.com/lightpanda-io/gomcp (Apache 2.0)

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
)

func runstd(ctx context.Context, stdin io.Reader, stdout io.Writer, mcpsrv *MCPServer) error {
	mcpconn := mcpsrv.NewConn()
	defer mcpconn.Close()

	send := func(_ string, data any) error {
		b, err := json.Marshal(data)
		if err != nil {
			return fmt.Errorf("marshal: %w", err)
		}
		b = append(b, '\n')

		_, err = stdout.Write(b)
		return err
	}

	for {
		buf, err := readNextMessage(stdin)
		if err != nil {
			return fmt.Errorf("read: %w", err)
		}
		if buf == nil {
			slog.Debug("stdin closed")
			return nil
		}

		rreq, err := mcpsrv.Decode(bytes.NewReader(buf))
		if err != nil {
			slog.Error("decode", slog.Any("err", err))
			continue
		}

		if err := mcpsrv.Handle(ctx, rreq, mcpconn, send); err != nil {
			slog.Error("handle", slog.Any("err", err))
		}
	}
}

func readNextMessage(r io.Reader) ([]byte, error) {
	buf := make([]byte, 0, 4096)
	tmp := make([]byte, 256)

	for {
		n, err := r.Read(tmp)
		if err == io.EOF {
			if len(buf) == 0 {
				return nil, nil
			}
			return buf, nil
		}
		if err != nil {
			return nil, err
		}

		buf = append(buf, tmp[:n]...)

		if bytes.Contains(buf, []byte("\n")) {
			return buf, nil
		}
	}
}
