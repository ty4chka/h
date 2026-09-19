package modules

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

type Module struct {
	File        string
	Dir         string
	FName       string
	Name        string
	Version     string
	Author      string
	Description string
	Commands    []string
	Type        string
	Size        int64
	Lines       int
}

type Scanner struct {
	Modules []Module
}

func NewScanner() *Scanner {
	s := &Scanner{}
	s.Scan()
	return s
}

func (s *Scanner) Scan() {
	s.Modules = nil
	for _, dir := range []string{"modules", "modules/mcub_mods"} {
		entries, err := os.ReadDir(dir)
		if err != nil {
			continue
		}
		for _, entry := range entries {
			if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".py") || strings.HasPrefix(entry.Name(), "_") {
				continue
			}
			fpath := filepath.Join(dir, entry.Name())
			mod := s.parseModule(fpath, dir)
			s.Modules = append(s.Modules, mod)
		}
	}
	sort.Slice(s.Modules, func(i, j int) bool {
		if s.Modules[i].Type != s.Modules[j].Type {
			return s.Modules[i].Type == "Hydra"
		}
		return strings.ToLower(s.Modules[i].Name) < strings.ToLower(s.Modules[j].Name)
	})
}

func (s *Scanner) parseModule(fpath, dir string) Module {
	fname := filepath.Base(fpath)
	name := strings.TrimSuffix(fname, ".py")
	mod := Module{
		File:        fpath,
		Dir:         dir,
		FName:       fname,
		Name:        name,
		Version:     "?",
		Author:      "unknown",
		Description: "No description",
		Type:        "MCUB",
	}
	if !strings.Contains(dir, "mcub") {
		mod.Type = "Hydra"
	}

	info, err := os.Stat(fpath)
	if err == nil {
		mod.Size = info.Size()
	}

	data, err := os.ReadFile(fpath)
	if err != nil {
		return mod
	}
	code := string(data)
	mod.Lines = strings.Count(code, "\n") + 1

	// Simple regex parsing for Python module metadata
	reName := regexp.MustCompile(`(?m)^name\s*=\s*["']([^"']+)["']`)
	reVer := regexp.MustCompile(`(?m)^version\s*=\s*["']([^"']+)["']`)
	reAuth := regexp.MustCompile(`(?m)^author\s*=\s*["']([^"']+)["']`)
	reDesc := regexp.MustCompile(`(?m)^description\s*=\s*["']([^"']+)["']`)
	reCmd := regexp.MustCompile(`(?m)@\w+\.command\s*\(\s*["']([^"']+)["']`)

	if m := reName.FindStringSubmatch(code); len(m) > 1 {
		mod.Name = m[1]
	}
	if m := reVer.FindStringSubmatch(code); len(m) > 1 {
		mod.Version = m[1]
	}
	if m := reAuth.FindStringSubmatch(code); len(m) > 1 {
		mod.Author = m[1]
	}
	if m := reDesc.FindStringSubmatch(code); len(m) > 1 {
		mod.Description = m[1]
	}
	for _, m := range reCmd.FindAllStringSubmatch(code, -1) {
		if len(m) > 1 {
			mod.Commands = append(mod.Commands, m[1])
		}
	}

	return mod
}
