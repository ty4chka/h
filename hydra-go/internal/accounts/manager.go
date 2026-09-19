package accounts

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"
)

var (
	AccountsFile = "data/accounts.json"
	BackupDir  = "data/backups"
)

type Account struct {
	Phone       string    `json:"phone"`
	Session     string    `json:"session"`
	Username    string    `json:"username"`
	FirstName   string    `json:"first_name"`
	CreatedAt   time.Time `json:"created_at"`
	LastUsed    *time.Time `json:"last_used"`
	LoginMethod string    `json:"login_method"`
	Favorite    bool      `json:"favorite"`
}

type Manager struct {
	Accounts map[string]Account
}

func NewManager() *Manager {
	m := &Manager{Accounts: make(map[string]Account)}
	m.Load()
	return m
}

func (m *Manager) Load() {
	data, err := os.ReadFile(AccountsFile)
	if err != nil {
		return
	}
	json.Unmarshal(data, &m.Accounts)
}

func (m *Manager) Save() error {
	os.MkdirAll(filepath.Dir(AccountsFile), 0755)
	m.createBackup()
	data, err := json.MarshalIndent(m.Accounts, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(AccountsFile, data, 0644)
}

func (m *Manager) createBackup() {
	if _, err := os.Stat(AccountsFile); os.IsNotExist(err) {
		return
	}
	os.MkdirAll(BackupDir, 0755)
	timestamp := time.Now().Format("20060102_150405")
	backupPath := filepath.Join(BackupDir, fmt.Sprintf("accounts_%s.json", timestamp))
	data, _ := os.ReadFile(AccountsFile)
	os.WriteFile(backupPath, data, 0644)

	// Keep only last 10 backups
	files, _ := filepath.Glob(filepath.Join(BackupDir, "accounts_*.json"))
	sort.Strings(files)
	if len(files) > 10 {
		for _, f := range files[:len(files)-10] {
			os.Remove(f)
		}
	}
}

func (m *Manager) Add(name, phone, session, username, firstName, method string) bool {
	if _, exists := m.Accounts[name]; exists {
		return false
	}
	m.Accounts[name] = Account{
		Phone:       phone,
		Session:     session,
		Username:    username,
		FirstName:   firstName,
		CreatedAt:   time.Now(),
		LoginMethod: method,
		Favorite:    false,
	}
	m.Save()
	return true
}

func (m *Manager) Remove(name string) bool {
	if _, exists := m.Accounts[name]; !exists {
		return false
	}
	sessionFile := m.Accounts[name].Session + ".session"
	os.Remove(sessionFile)
	delete(m.Accounts, name)
	m.Save()
	return true
}

func (m *Manager) Get(name string) (Account, bool) {
	acc, ok := m.Accounts[name]
	return acc, ok
}

func (m *Manager) List() []string {
	names := make([]string, 0, len(m.Accounts))
	for name := range m.Accounts {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func (m *Manager) Exists(name string) bool {
	_, ok := m.Accounts[name]
	return ok
}

func (m *Manager) UpdateLastUsed(name string) {
	if acc, ok := m.Accounts[name]; ok {
		now := time.Now()
		acc.LastUsed = &now
		m.Accounts[name] = acc
		m.Save()
	}
}

func (m *Manager) ToggleFavorite(name string) bool {
	if acc, ok := m.Accounts[name]; ok {
		acc.Favorite = !acc.Favorite
		m.Accounts[name] = acc
		m.Save()
		return acc.Favorite
	}
	return false
}

func (m *Manager) BackupCount() int {
	files, _ := filepath.Glob(filepath.Join(BackupDir, "accounts_*.json"))
	return len(files)
}

func (m *Manager) Backups() []string {
	files, _ := filepath.Glob(filepath.Join(BackupDir, "accounts_*.json"))
	sort.Strings(files)
	return files
}
