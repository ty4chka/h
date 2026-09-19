package logger

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

var LogFile = "data/hydra.log"

type Logger struct {
	file *os.File
}

func New() *Logger {
	os.MkdirAll(filepath.Dir(LogFile), 0755)
	f, _ := os.OpenFile(LogFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	return &Logger{file: f}
}

func (l *Logger) Log(level, msg string) {
	timestamp := time.Now().Format("2006-01-02 15:04:05")
	line := fmt.Sprintf("%s | %-8s | %s\n", timestamp, level, msg)
	if l.file != nil {
		l.file.WriteString(line)
	}
}

func (l *Logger) Info(msg string)  { l.Log("INFO", msg) }
func (l *Logger) Warn(msg string)  { l.Log("WARNING", msg) }
func (l *Logger) Error(msg string) { l.Log("ERROR", msg) }

func (l *Logger) ReadLast(n int) []string {
	data, err := os.ReadFile(LogFile)
	if err != nil {
		return []string{"No logs yet"}
	}
	lines := strings.Split(string(data), "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	return lines
}

func (l *Logger) Clear() error {
	if l.file != nil {
		l.file.Close()
	}
	return os.WriteFile(LogFile, []byte{}, 0644)
}

func (l *Logger) Size() int64 {
	info, err := os.Stat(LogFile)
	if err != nil {
		return 0
	}
	return info.Size()
}
