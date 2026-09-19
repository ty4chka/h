// Hydra Go core: быстрые операции ядра + запуск Go-модулей.
// Общение с Python-ядром — JSON-строки по stdio (hydra_kernel.kernel.gobridge).
package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"time"
)

type Req struct {
	ID     int      `json:"id"`
	Op     string   `json:"op"`
	Text   string   `json:"text,omitempty"`
	Path   string   `json:"path,omitempty"`
	Data   string   `json:"data,omitempty"`
	Module string   `json:"module,omitempty"`
	Args   []string `json:"args,omitempty"`
}

type Resp struct {
	ID     int    `json:"id"`
	Ok     bool   `json:"ok"`
	Result string `json:"result,omitempty"`
	Error  string `json:"error,omitempty"`
}

var ansiRe = regexp.MustCompile(`\x1b\[[0-9;]*[mABCDEFGHJKSTfhilmnprsu]`)

var started = time.Now()

func modulesDir() string {
	exe, err := os.Executable()
	if err != nil {
		return "gocore/bin"
	}
	return filepath.Join(filepath.Dir(exe), "bin")
}

func handle(r Req) Resp {
	resp := Resp{ID: r.ID, Ok: true}
	switch r.Op {
	case "ping":
		resp.Result = fmt.Sprintf("pong: go core up %s", time.Since(started).Round(time.Millisecond))
	case "ansi_strip":
		resp.Result = ansiRe.ReplaceAllString(r.Text, "")
	case "sha256":
		sum := sha256.Sum256([]byte(r.Text))
		resp.Result = hex.EncodeToString(sum[:])
	case "read_file":
		b, err := os.ReadFile(r.Path)
		if err != nil {
			resp.Ok, resp.Error = false, err.Error()
		} else {
			resp.Result = string(b)
		}
	case "write_file":
		err := os.WriteFile(r.Path, []byte(r.Data), 0o644)
		if err != nil {
			resp.Ok, resp.Error = false, err.Error()
		} else {
			resp.Result = "written"
		}
	case "modules":
		entries, err := os.ReadDir(modulesDir())
		if err != nil {
			resp.Ok, resp.Error = false, err.Error()
			break
		}
		names := []string{}
		for _, e := range entries {
			if !e.IsDir() {
				names = append(names, e.Name())
			}
		}
		b, _ := json.Marshal(names)
		resp.Result = string(b)
	case "run_module":
		bin := filepath.Join(modulesDir(), r.Module)
		cmd := exec.Command(bin, r.Args...)
		out, err := cmd.CombinedOutput()
		if err != nil {
			resp.Ok, resp.Error = false, err.Error()
		}
		resp.Result = string(out)
	default:
		resp.Ok, resp.Error = false, "unknown op: "+r.Op
	}
	return resp
}

func main() {
	sc := bufio.NewScanner(os.Stdin)
	sc.Buffer(make([]byte, 1024*1024), 1024*1024)
	out := bufio.NewWriter(os.Stdout)
	for sc.Scan() {
		var r Req
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			fmt.Fprintf(out, `{"id":0,"ok":false,"error":"bad json: %s"}`+"\n", err.Error())
			out.Flush()
			continue
		}
		b, _ := json.Marshal(handle(r))
		fmt.Fprintln(out, string(b))
		out.Flush()
	}
}
