// OrcaView's Windows launcher. Its PE overlay is a standard ZIP containing
// the target-native runtime. Each process owns its private temporary copy.
package main

import (
	"archive/zip"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

func unpackFile(entry *zip.File, root string) error {
	name, err := filepath.Localize(entry.Name)
	if err != nil || !strings.HasPrefix(entry.Name, "python/") || !entry.Mode().IsRegular() {
		return fmt.Errorf("invalid runtime file %q", entry.Name)
	}
	dest := filepath.Join(root, name)
	if err := os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
		return err
	}
	src, err := entry.Open()
	if err != nil {
		return err
	}
	defer src.Close()
	f, err := os.OpenFile(dest, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(f, src)
	return errors.Join(copyErr, f.Close())
}

func unpack(executable, root string) error {
	archive, err := zip.OpenReader(executable)
	if err != nil {
		return err
	}
	defer archive.Close()
	for _, entry := range archive.File {
		if entry.Name != "orcaview-windows.json" {
			if err := unpackFile(entry, root); err != nil {
				return err
			}
		}
	}
	return nil
}

// A Windows GUI process inherits redirected pipes but usually no console.
// Attach to the invoking terminal for CLI use and preserve explicit redirects.
func consoleFile(inherited *os.File, device string, mode int) *os.File {
	if _, err := inherited.Stat(); err == nil {
		return inherited
	}
	f, _ := os.OpenFile(device, mode, 0)
	return f
}

func cleanup(root string) {
	// A native library may briefly remain open as a child finishes exiting.
	for i := 0; i < 5; i++ {
		if os.RemoveAll(root) == nil {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
}

func launch() (int, error) {
	executable, err := os.Executable()
	if err != nil {
		return 1, err
	}
	root, err := os.MkdirTemp("", "OrcaView-")
	if err != nil {
		return 1, err
	}
	defer cleanup(root)
	if err := unpack(executable, root); err != nil {
		return 1, err
	}
	args := os.Args[1:]
	if len(args) == 0 {
		args = []string{"gui"}
	}
	python := "pythonw.exe"
	if args[0] != "gui" {
		python = "python.exe"
	}
	cmd := exec.Command(filepath.Join(root, "python", python), append([]string{"-I", "-B", "-m", "orcaview"}, args...)...)
	cmd.Env = append(os.Environ(), "ORCAVIEW_PORTABLE_EXE="+executable, "ORCAVIEW_PORTABLE_PID="+strconv.Itoa(os.Getpid()))
	if python == "python.exe" {
		const attachParent = 0xffffffff
		syscall.NewLazyDLL("kernel32.dll").NewProc("AttachConsole").Call(attachParent)
		if f := consoleFile(os.Stdin, "CONIN$", os.O_RDONLY); f != nil {
			cmd.Stdin = f
		}
		if f := consoleFile(os.Stdout, "CONOUT$", os.O_WRONLY); f != nil {
			cmd.Stdout = f
		}
		if f := consoleFile(os.Stderr, "CONOUT$", os.O_WRONLY); f != nil {
			cmd.Stderr = f
		}
		cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	}
	if err := cmd.Run(); err != nil {
		var exit *exec.ExitError
		if errors.As(err, &exit) {
			return exit.ExitCode(), nil
		}
		return 1, err
	}
	return 0, nil
}

func main() {
	code, err := launch()
	if err != nil {
		if len(os.Args) > 1 && os.Args[1] != "gui" {
			fmt.Fprintln(os.Stderr, err)
		} else {
			message, _ := syscall.UTF16PtrFromString(err.Error())
			title, _ := syscall.UTF16PtrFromString("OrcaView")
			syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(message)), uintptr(unsafe.Pointer(title)), 0x10)
		}
	}
	os.Exit(code)
}
