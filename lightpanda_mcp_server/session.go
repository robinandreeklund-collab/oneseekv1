// Based on github.com/lightpanda-io/gomcp (Apache 2.0)

package main

import (
	"errors"
	"sync"

	"github.com/google/uuid"
	"github.com/robinandreeklund-collab/oneseekv1/lightpanda_mcp_server/mcp"
)

type SessionId uuid.UUID

var InvalidSessionId = errors.New("invalid session id")

func (id SessionId) String() string {
	return uuid.UUID(id).String()
}

func (id *SessionId) Set(v string) error {
	if len(v) == 0 {
		return InvalidSessionId
	}
	u, err := uuid.Parse(v)
	if err != nil {
		return InvalidSessionId
	}
	*id = SessionId(u)
	return nil
}

type Sessions struct {
	mu       sync.Mutex
	sessions map[SessionId]*Session
}

func NewSessions() *Sessions {
	return &Sessions{
		sessions: make(map[SessionId]*Session),
	}
}

func (s *Sessions) Add(session *Session) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sessions[session.id] = session
}

func (s *Sessions) Get(id SessionId) (*Session, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	session, ok := s.sessions[id]
	return session, ok
}

func (s *Sessions) Remove(id SessionId) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.sessions, id)
}

type Session struct {
	id   SessionId
	creq chan mcp.Request
}

func NewSession() *Session {
	return &Session{
		id:   SessionId(uuid.New()),
		creq: make(chan mcp.Request),
	}
}

func (s *Session) Requests() chan mcp.Request {
	return s.creq
}

func (s *Session) Close() {
	close(s.creq)
}
