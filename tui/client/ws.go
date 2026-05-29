package client

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

const dialTimeout = 4 * time.Second

type Event interface{}

type ConnectedEvent struct {
	URL             string
	ContractVersion string
}

type DisconnectedEvent struct {
	Err error
}

type StreamEvent struct {
	RequestID   string
	SessionID   string
	Text        string
	Accumulated string
	Done        bool
	Degraded    bool
	Error       string
	Model       string
}

type ResponseEvent struct {
	RequestID string
	SessionID string
	Text      string
	Model     string
}

type RequestErrorEvent struct {
	RequestID   string
	Code        string
	Message     string
	StatusCode  int
	RetryAfterS *float64
}

type Client struct {
	url    string
	events chan Event

	mu        sync.Mutex
	conn      *websocket.Conn
	connected bool
	nextID    uint64
	closed    bool
}

func New(url string) *Client {
	return &Client{
		url:    url,
		events: make(chan Event, 32),
	}
}

func (c *Client) Events() <-chan Event {
	return c.events
}

func (c *Client) Connect(ctx context.Context) error {
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return errors.New("client closed")
	}
	if c.connected && c.conn != nil {
		c.mu.Unlock()
		return nil
	}
	if c.conn != nil {
		_ = c.conn.Close()
		c.conn = nil
	}
	c.connected = false
	c.mu.Unlock()

	if _, ok := ctx.Deadline(); !ok {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, dialTimeout)
		defer cancel()
	}

	conn, _, err := websocket.DefaultDialer.DialContext(ctx, c.url, nil)
	if err != nil {
		return err
	}

	challenge, err := c.readFrame(conn)
	if err != nil {
		_ = conn.Close()
		return err
	}
	if challenge.Type != "event" || challenge.Event != "connect.challenge" {
		_ = conn.Close()
		return fmt.Errorf("unexpected first frame: type=%q event=%q", challenge.Type, challenge.Event)
	}

	connectID := c.NextRequestID("connect")
	if err := conn.WriteJSON(map[string]any{
		"type":   "req",
		"id":     connectID,
		"method": "connect",
		"params": map[string]any{},
	}); err != nil {
		_ = conn.Close()
		return err
	}

	response, err := c.readFrame(conn)
	if err != nil {
		_ = conn.Close()
		return err
	}
	if response.Type != "res" || response.ID != connectID {
		_ = conn.Close()
		return fmt.Errorf("unexpected connect response: type=%q id=%q", response.Type, response.ID)
	}
	if !response.OK {
		_ = conn.Close()
		return fmt.Errorf("connect failed: %s", response.Error.Message)
	}

	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		_ = conn.Close()
		return errors.New("client closed")
	}
	c.conn = conn
	c.connected = true
	c.mu.Unlock()

	go c.readLoop(conn)
	c.emit(ConnectedEvent{URL: c.url, ContractVersion: response.Result.ContractVersion})
	return nil
}

func (c *Client) Reconnect(ctx context.Context) error {
	_ = c.CloseConnection()
	return c.Connect(ctx)
}

func (c *Client) SendChat(ctx context.Context, requestID string, sessionID string, text string) error {
	if err := c.Connect(ctx); err != nil {
		return err
	}

	payload := map[string]any{
		"type":   "req",
		"id":     requestID,
		"method": "chat.send",
		"params": map[string]any{
			"session_id": sessionID,
			"text":       text,
			"stream":     true,
		},
	}

	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.connected || c.conn == nil {
		return errors.New("not connected")
	}
	if err := c.conn.WriteJSON(payload); err != nil {
		c.connected = false
		_ = c.conn.Close()
		c.conn = nil
		return err
	}
	return nil
}

func (c *Client) CloseConnection() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.connected = false
	if c.conn == nil {
		return nil
	}
	err := c.conn.Close()
	c.conn = nil
	return err
}

func (c *Client) Close() error {
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return nil
	}
	c.closed = true
	conn := c.conn
	c.conn = nil
	c.connected = false
	c.mu.Unlock()
	if conn != nil {
		_ = conn.Close()
	}
	return nil
}

func (c *Client) readLoop(conn *websocket.Conn) {
	for {
		frame, err := c.readFrame(conn)
		if err != nil {
			c.mu.Lock()
			wasActive := c.conn == conn
			if c.conn == conn {
				c.conn = nil
				c.connected = false
			}
			closed := c.closed
			c.mu.Unlock()
			if wasActive && !closed {
				c.emit(DisconnectedEvent{Err: err})
			}
			return
		}

		switch {
		case frame.Type == "event" && frame.Event == "chat.chunk":
			c.emit(StreamEvent{
				RequestID:   frame.ID,
				SessionID:   frame.Params.SessionID,
				Text:        frame.Params.Text,
				Accumulated: frame.Params.Accumulated,
				Done:        frame.Params.Done,
				Degraded:    frame.Params.Degraded,
				Error:       frame.Params.Error,
				Model:       frame.Params.Model,
			})
		case frame.Type == "res" && frame.OK:
			c.emit(ResponseEvent{
				RequestID: frame.ID,
				SessionID: frame.Result.SessionID,
				Text:      frame.Result.Text,
				Model:     frame.Result.Model,
			})
		case frame.Type == "res" && !frame.OK:
			c.emit(RequestErrorEvent{
				RequestID:   frame.ID,
				Code:        frame.Error.Code,
				Message:     frame.Error.Message,
				StatusCode:  frame.Error.StatusCode,
				RetryAfterS: frame.Error.RetryAfterS,
			})
		}
	}
}

func (c *Client) readFrame(conn *websocket.Conn) (frame, error) {
	var payload frame
	if err := conn.ReadJSON(&payload); err != nil {
		return frame{}, err
	}
	return payload, nil
}

func (c *Client) NextRequestID(prefix string) string {
	n := atomic.AddUint64(&c.nextID, 1)
	return fmt.Sprintf("%s-%d", prefix, n)
}

func (c *Client) emit(event Event) {
	c.events <- event
}

type frame struct {
	Type   string       `json:"type"`
	Event  string       `json:"event"`
	ID     string       `json:"id"`
	OK     bool         `json:"ok"`
	Params frameParams  `json:"params"`
	Result frameResult  `json:"result"`
	Error  frameError   `json:"error"`
}

type frameParams struct {
	SessionID   string `json:"session_id"`
	Text        string `json:"text"`
	Accumulated string `json:"accumulated"`
	Done        bool   `json:"done"`
	Degraded    bool   `json:"degraded"`
	Error       string `json:"error"`
	Model       string `json:"model"`
}

type frameResult struct {
	Connected       bool   `json:"connected"`
	ContractVersion string `json:"contract_version"`
	SessionID       string `json:"session_id"`
	Text            string `json:"text"`
	Model           string `json:"model"`
}

type frameError struct {
	Code        string `json:"code"`
	Message     string `json:"message"`
	StatusCode  int    `json:"status_code"`
	RetryAfterS *float64 `json:"retry_after_s"`
}

func (f *frame) UnmarshalJSON(data []byte) error {
	type rawFrame frame
	var raw rawFrame
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	*f = frame(raw)
	return nil
}
