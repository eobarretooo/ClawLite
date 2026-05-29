package views

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	"github.com/charmbracelet/lipgloss"
)

type Message struct {
	Role      string
	Text      string
	Model     string
	Streaming bool
	Error     bool
}

type ChatView struct {
	appBorder       lipgloss.Style
	header          lipgloss.Style
	statusGood      lipgloss.Style
	statusWarn      lipgloss.Style
	statusBad       lipgloss.Style
	userLabel       lipgloss.Style
	assistantLabel  lipgloss.Style
	errorLabel      lipgloss.Style
	messageBody     lipgloss.Style
	footer          lipgloss.Style
	inputBorder     lipgloss.Style
	placeholderNote lipgloss.Style
}

func NewChatView() ChatView {
	return ChatView{
		appBorder:       lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("240")).Padding(0, 1),
		header:          lipgloss.NewStyle().Foreground(lipgloss.Color("230")).Bold(true),
		statusGood:      lipgloss.NewStyle().Foreground(lipgloss.Color("42")),
		statusWarn:      lipgloss.NewStyle().Foreground(lipgloss.Color("214")),
		statusBad:       lipgloss.NewStyle().Foreground(lipgloss.Color("203")),
		userLabel:       lipgloss.NewStyle().Foreground(lipgloss.Color("111")).Bold(true),
		assistantLabel:  lipgloss.NewStyle().Foreground(lipgloss.Color("219")).Bold(true),
		errorLabel:      lipgloss.NewStyle().Foreground(lipgloss.Color("203")).Bold(true),
		messageBody:     lipgloss.NewStyle().Foreground(lipgloss.Color("252")),
		footer:          lipgloss.NewStyle().Foreground(lipgloss.Color("245")),
		inputBorder:     lipgloss.NewStyle().Border(lipgloss.NormalBorder()).BorderForeground(lipgloss.Color("240")).Padding(0, 1),
		placeholderNote: lipgloss.NewStyle().Foreground(lipgloss.Color("244")).Italic(true),
	}
}

func (v ChatView) Render(width int, height int, history viewport.Model, input textinput.Model, statusLabel string, statusKind string, gatewayURL string) string {
	innerWidth := maxInt(20, width-4)
	header := lipgloss.JoinHorizontal(lipgloss.Top,
		v.header.Render("ClawLite Go TUI v0.1"),
		"  ",
		v.renderStatus(statusLabel, statusKind),
	)
	urlLine := v.footer.Render(gatewayURL)
	inputBox := v.inputBorder.Width(innerWidth).Render(input.View())
	footer := v.footer.Render("Enter send | Ctrl+R reconnect | PgUp/PgDn scroll | Esc/Ctrl+C/q quit")
	body := lipgloss.JoinVertical(lipgloss.Left, header, urlLine, history.View(), inputBox, footer)
	return v.appBorder.Width(maxInt(24, width-2)).Height(maxInt(10, height-1)).Render(body)
}

func (v ChatView) Transcript(messages []Message, width int) string {
	if len(messages) == 0 {
		return v.placeholderNote.Width(width).Render("No messages yet. Type a prompt and press Enter.")
	}

	parts := make([]string, 0, len(messages))
	for _, msg := range messages {
		label := v.assistantLabel.Render("Assistant")
		if msg.Role == "user" {
			label = v.userLabel.Render("You")
		} else if msg.Error {
			label = v.errorLabel.Render("Error")
		}

		meta := ""
		if msg.Model != "" {
			meta = v.footer.Render("  [" + msg.Model + "]")
		}
		if msg.Streaming {
			meta += v.footer.Render("  streaming")
		}

		text := strings.TrimSpace(msg.Text)
		if text == "" && msg.Streaming {
			text = "..."
		}
		body := v.messageBody.Width(width).Render(text)
		parts = append(parts, fmt.Sprintf("%s%s\n%s", label, meta, body))
	}
	return strings.Join(parts, "\n\n")
}

func (v ChatView) renderStatus(label string, kind string) string {
	s := v.statusWarn
	if kind == "good" {
		s = v.statusGood
	}
	if kind == "bad" {
		s = v.statusBad
	}
	return s.Render(label)
}

func maxInt(a int, b int) int {
	if a > b {
		return a
	}
	return b
}
