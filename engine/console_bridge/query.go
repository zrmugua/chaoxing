//go:build consolebridge

// This entry adds read-only queries for the management UI. Ordinary execution
// continues through the original yatori-go-console main function.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	ort "github.com/yalue/onnxruntime_go"
	core "github.com/yatori-dev/yatori-go-core/aggregation/xuexitong"
	lg "github.com/yatori-dev/yatori-go-core/utils/log"
	"yatori-go-console/config"
	consoleinit "yatori-go-console/init"
	consolexxt "yatori-go-console/logic/xuexitong"
	consoleutils "yatori-go-console/utils"
)

var bridgeVersion = "0.7.0"

const bridgeConsoleCommit = "017711107803f5232fea59446a5b8c801d4ca8b2"

type bridgeResult struct {
	OK    bool   `json:"ok"`
	Data  any    `json:"data,omitempty"`
	Error string `json:"error,omitempty"`
}

func init() {
	if os.Getenv("YATORI_MANAGED") == "1" {
		parent := os.Getppid()
		go func() {
			for {
				time.Sleep(time.Second)
				if parent <= 1 || os.Getppid() != parent {
					os.Exit(125)
				}
			}
		}()
	}
	mode := os.Getenv("YATORI_BRIDGE_MODE")
	if mode == "" {
		return
	}
	result, err := bridgeQuery(mode)
	code := 0
	response := bridgeResult{OK: err == nil, Data: result}
	if err != nil {
		fmt.Println("Console 查询：", err)
		response.Error = "原版 Console 查询未成功，请查看运行日志"
		code = 2
	}
	encoded, err := json.Marshal(response)
	if err != nil || os.WriteFile("query-result.json", encoded, 0600) != nil {
		os.Exit(3)
	}
	os.Exit(code)
}

func bridgeQuery(mode string) (any, error) {
	metadata := map[string]any{"version": bridgeVersion, "console_commit": bridgeConsoleCommit,
		"execution": "yatori-go-console", "os": runtime.GOOS, "arch": runtime.GOARCH}
	if mode == "metadata" {
		return metadata, nil
	}
	if mode != "selftest" && mode != "courses" && mode != "chapters" && mode != "assessments" {
		return nil, fmt.Errorf("unknown query mode")
	}
	consoleinit.YatoriConsoleInit()
	if mode == "selftest" {
		directory := os.Getenv("YATORI_MODEL_DIR")
		if directory == "" {
			directory = "assets"
		}
		for _, name := range []string{"common_old.onnx", "common_tencent.onnx", "calc_det.onnx"} {
			inputs, outputs, err := ort.GetInputOutputInfo(filepath.Join(directory, name))
			if err != nil || len(inputs) == 0 || len(outputs) == 0 {
				return nil, fmt.Errorf("OCR model initialization failed: %s", name)
			}
		}
		metadata["models_checked"] = 3
		return metadata, nil
	}
	settings := config.ReadConfig("config.yaml")
	if len(settings.Users) != 1 || settings.Users[0].AccountType != "XUEXITONG" {
		return nil, fmt.Errorf("one XUEXITONG account is required")
	}
	lg.LogInit(lg.StringToLOGLEVEL(settings.Setting.BasicSetting.LogLevel), false, 0, "")
	if settings.Users[0].IsProxy == 1 {
		data, err := os.ReadFile("ip.txt")
		if err != nil {
			return nil, fmt.Errorf("proxy configuration unavailable")
		}
		proxy := strings.TrimSpace(string(data))
		if _, _, err := consoleutils.CheckProxyIp(proxy); err != nil {
			return nil, fmt.Errorf("proxy connection failed")
		}
		consoleutils.IsProxyFlag = true
		consoleutils.IPProxyPool = []string{proxy}
	}
	caches := consolexxt.UserLoginOperation(settings.Users)
	if len(caches) != 1 {
		return nil, fmt.Errorf("account login failed")
	}
	cache := caches[0]
	if mode == "courses" {
		courses, err := core.XueXiTPullCourseAction(cache)
		if err != nil {
			return nil, err
		}
		result := []map[string]any{}
		for _, c := range courses {
			result = append(result, map[string]any{"courseId": c.CourseID, "clazzId": c.Key,
				"cpi": strconv.Itoa(c.Cpi), "title": c.CourseName, "teacher": c.CourseTeacher,
				"progress": c.JobRate, "original": c})
		}
		return result, nil
	}
	var query struct {
		Course core.XueXiTCourse `json:"course"`
	}
	data, err := os.ReadFile("query.json")
	if err != nil || len(data) > 100000 || json.Unmarshal(data, &query) != nil {
		return nil, fmt.Errorf("invalid course query")
	}
	course := query.Course
	classID, err := strconv.Atoi(course.Key)
	if err != nil || classID <= 0 || course.CourseID == "" {
		return nil, fmt.Errorf("invalid course identity")
	}
	if mode == "chapters" {
		chapters, _, err := core.PullCourseChapterAction(cache, course.Cpi, classID)
		if err != nil {
			return nil, err
		}
		nodes := []int{}
		for _, c := range chapters.Knowledge {
			nodes = append(nodes, c.ID)
		}
		userID, _ := strconv.Atoi(cache.UserID)
		courseID, _ := strconv.Atoi(course.CourseID)
		states, err := core.ChapterFetchPointAction(cache, nodes, &chapters, classID, userID, course.Cpi, courseID)
		if err != nil {
			return nil, err
		}
		result := []map[string]any{}
		for _, c := range states.Knowledge {
			result = append(result, map[string]any{"id": strconv.Itoa(c.ID), "title": c.Name, "jobCount": c.PointTotal,
				"has_finished": c.PointTotal > 0 && c.PointTotal == c.PointFinished, "need_unlock": c.Status == "locked"})
		}
		return result, nil
	}
	result := []map[string]any{}
	works, err := core.PullWorkListAction(cache, course)
	if err != nil {
		return nil, err
	}
	for _, work := range works {
		result = append(result, map[string]any{"id": work.TaskRefId, "kind": "work", "title": work.Name, "status": work.Status, "remaining": work.RemainTime})
	}
	exams, err := core.PullExamListAction(cache, course)
	if err != nil {
		return nil, err
	}
	for _, exam := range exams {
		result = append(result, map[string]any{"id": exam.TaskRefId, "kind": "exam", "title": exam.Name, "status": exam.Status, "remaining": exam.RemainTime})
	}
	return result, nil
}
