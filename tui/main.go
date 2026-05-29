package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"clawlite/tui/client"
	"clawlite/tui/views"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
)

const defaultGatewayURL = "ws://127.0.0.1:8787/ws"

type connectResultMsg struct {
	Err error
}

type sendResultMsg struct {
	Err       error
}

type model struct {
	client    *client.Client
	view      views.ChatView
	history   viewport.Model
	input     textinput.Model
	messages  []views.Message
	sessionID string
	url       string

	statusText string
	statusKind string
	pendingID  string
	width      int
	height     int
	connected  bool
	quitting   bool
}

func main() {
	url := strings.TrimSpace(os.Getenv("CLAWLITE_GATEWAY_URL"))
	if url == "" {
		url = defaultGatewayURL
	}

	input := textinput.New()
	input.Placeholder = "Send a message"
	input.Focus()
	input.CharLimit = 4000
	input.Prompt = "> "

	history := viewport.New(0, 0)

	m := model{
		client:     client.New(url),
		view:       views.NewChatView(),
		history:    history,
		input:      input,
		sessionID:  fmt.Sprintf("tui:%d", time.Now().UnixNano()),
		url:        url,
		statusText: "connecting",
		statusKind: "warn",
	}

	p := tea.NewProgram(m, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func (m model) Init() tea.Cmd {
	return tea.Batch(m.connectCmd(false), m.waitForEvent())
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.resize()
		return m, nil
	case tea.KeyMsg:
		if msg.Type == tea.KeyCtrlC || msg.Type == tea.KeyEsc {
			m.quitting = true
			_ = m.client.Close()
			return m, tea.Quit
		}
		if msg.String() == "q" && strings.TrimSpace(m.input.Value()) == "" {
			m.quitting = true
			_ = m.client.Close()
			return m, tea.Quit
		}
		if msg.Type == tea.KeyCtrlR {
			m.statusText = "connecting"
			m.statusKind = "warn"
			return m, m.connectCmd(true)
		}
		if msg.Type == tea.KeyEnter {
			if m.pendingID != "" {
				return m, nil
			}
			text := strings.TrimSpace(m.input.Value())
			if text == "" {
				return m, nil
			}
			m.messages = append(m.messages,
				views.Message{Role: "user", Text: text},
				views.Message{Role: "assistant", Streaming: true},
			)
			m.input.SetValue("")
			m.pendingID = m.client.NextRequestID("chat")
			m.statusText = "streaming"
			m.statusKind = "warn"
			m.refreshTranscript(true)
			return m, m.sendCmd(m.pendingID, text)
		}
		if isViewportKey(msg) {
			var cmd tea.Cmd
			m.history, cmd = m.history.Update(msg)
			return m, cmd
		}
		var cmd tea.Cmd
		m.input, cmd = m.input.Update(msg)
		return m, cmd
	case connectResultMsg:
		if msg.Err != nil {
			m.connected = false
			m.statusText = shortStatus("connection error", msg.Err)
			m.statusKind = "bad"
		}
		return m, nil
	case sendResultMsg:
		if msg.Err != nil {
			m.connected = false
			m.pendingID = ""
			m.failPending(shortStatus("send failed", msg.Err))
			return m, nil
		}
		return m, nil
	case client.ConnectedEvent:
		m.connected = true
		if m.pendingID == "" {
			m.statusText = "connected"
			m.statusKind = "good"
		}
		return m, m.waitForEvent()
	case client.DisconnectedEvent:
		m.connected = false
		if m.pendingID != "" {
			m.failPending(shortStatus("disconnected", msg.Err))
		} else {
			m.statusText = shortStatus("disconnected", msg.Err)
			m.statusKind = "bad"
		}
		return m, m.waitForEvent()
	case client.StreamEvent:
		if msg.RequestID == m.pendingID {
			m.statusText = "streaming"
			m.statusKind = "warn"
			m.updateAssistant(msg.Accumulated, msg.Model, true, false)
		}
		return m, m.waitForEvent()
	case client.ResponseEvent:
		if msg.RequestID == m.pendingID {
			m.pendingID = ""
			m.connected = true
			m.statusText = "connected"
			m.statusKind = "good"
			m.updateAssistant(msg.Text, msg.Model, false, false)
		}
		return m, m.waitForEvent()
	case client.RequestErrorEvent:
		if msg.RequestID == m.pendingID {
			m.pendingID = ""
			m.statusText = fmt.Sprintf("request error %s", msg.Code)
			m.statusKind = "bad"
			m.updateAssistant(msg.Message, "", false, true)
		}
		return m, m.waitForEvent()
	default:
		return m, nil
	}
}

func (m model) View() string {
	return m.view.Render(m.width, m.height, m.history, m.input, m.statusText, m.statusKind, m.url)
}

func (m model) waitForEvent() tea.Cmd {
	return func() tea.Msg {
		return <-m.client.Events()
	}
}

func (m model) connectCmd(force bool) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
		defer cancel()
		var err error
		if force {
			err = m.client.Reconnect(ctx)
		} else {
			err = m.client.Connect(ctx)
		}
		return connectResultMsg{Err: err}
	}
}

func (m model) sendCmd(requestID string, text string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
		defer cancel()
		err := m.client.SendChat(ctx, requestID, m.sessionID, text)
		return sendResultMsg{Err: err}
	}
}

func (m *model) resize() {
	if m.width == 0 || m.height == 0 {
		m.width = 80
		m.height = 24
	}
	historyHeight := m.height - 8
	if historyHeight < 5 {
		historyHeight = 5
	}
	m.history.Width = maxInt(20, m.width-6)
	m.history.Height = historyHeight
	m.refreshTranscript(false)
	inputWidth := m.width - 8
	if inputWidth < 12 {
		inputWidth = 12
	}
	m.input.Width = inputWidth
}

func (m *model) refreshTranscript(goBottom bool) {
	content := m.view.Transcript(m.messages, maxInt(20, m.history.Width-1))
	m.history.SetContent(content)
	if goBottom {
		m.history.GotoBottom()
	}
	if len(m.messages) == 0 {
		m.history.GotoTop()
	}
}

func (m *model) updateAssistant(text string, modelName string, streaming bool, isError bool) {
	for i := len(m.messages) - 1; i >= 0; i-- {
		if m.messages[i].Role == "assistant" || m.messages[i].Error {
			m.messages[i].Text = text
			m.messages[i].Model = modelName
			m.messages[i].Streaming = streaming
			m.messages[i].Error = isError
			m.refreshTranscript(true)
			return
		}
	}
	m.messages = append(m.messages, views.Message{Role: "assistant", Text: text, Model: modelName, Streaming: streaming, Error: isError})
	m.refreshTranscript(true)
}

func (m *model) failPending(message string) {
	m.pendingID = ""
	m.statusText = message
	m.statusKind = "bad"
	m.updateAssistant(message, "", false, true)
}

func isViewportKey(msg tea.KeyMsg) bool {
	switch msg.Type {
	case tea.KeyUp, tea.KeyDown, tea.KeyPgUp, tea.KeyPgDown, tea.KeyHome, tea.KeyEnd:
		return true
	default:
		return false
	}
}

func shortStatus(prefix string, err error) string {
	if err == nil {
		return prefix
	}
	text := strings.TrimSpace(err.Error())
	if text == "" {
		return prefix
	}
	return prefix + ": " + text
}

func maxInt(a int, b int) int {
	if a > b {
		return a
	}
	return b
}
