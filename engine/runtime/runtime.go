package runtime

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	yatori "github.com/yatori-dev/yatori-go-core/api/xuexitong"
)

type failure string

func (e failure) Error() string { return string(e) }
func errorCode(err error) string {
	var known failure
	if errors.As(err, &known) {
		return string(known)
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return "execution_timeout"
	}
	var remote *yatori.RemoteError
	if errors.As(err, &remote) {
		return "remote_error"
	}
	return "network_error"
}

type Cookie struct {
	Name    string `json:"name"`
	Value   string `json:"value"`
	Domain  string `json:"domain"`
	Path    string `json:"path"`
	Secure  bool   `json:"secure"`
	Expires *int64 `json:"expires"`
}
type Course map[string]any
type Chapter struct {
	ID       string `json:"id"`
	Title    string `json:"title"`
	JobCount int    `json:"jobCount"`
	Finished bool   `json:"has_finished"`
	Locked   bool   `json:"need_unlock"`
}
type Job struct {
	ID        string         `json:"id"`
	ChapterID string         `json:"chapter_id"`
	Kind      string         `json:"kind"`
	Title     string         `json:"title"`
	Passed    bool           `json:"passed"`
	Card      int            `json:"card"`
	Metadata  map[string]any `json:"metadata"`
	Defaults  map[string]any `json:"defaults"`
}
type Runtime struct {
	cache            *yatori.XueXiTUserCache
	ctx              context.Context
	cancel           context.CancelFunc
	progress         func(float64)
	executionTimeout time.Duration
	transport        http.RoundTripper
	lastFailure      error
	jobs             map[string]Job
	now              func() time.Time
	wait             func(time.Duration) error
	currentCard      *int
	mediaClient      string
	papers           map[string]*paper
	assessmentsByID  map[string]assessmentTarget
	proxyURL         string
}

func New(args json.RawMessage) (*Runtime, error) {
	var initial struct {
		Credentials struct {
			Username    string  `json:"username"`
			Password    string  `json:"password"`
			Timeout     float64 `json:"execution_timeout"`
			MediaClient string  `json:"media_client"`
			ProxyURL    string  `json:"proxy_url"`
		} `json:"credentials"`
		Cookies []Cookie `json:"cookies"`
	}
	if json.Unmarshal(args, &initial) != nil {
		return nil, failure("adapter_error")
	}
	seconds := initial.Credentials.Timeout
	if seconds < 30 {
		seconds = 28800
	}
	if seconds > 86400 {
		seconds = 86400
	}
	r := &Runtime{cache: &yatori.XueXiTUserCache{Name: initial.Credentials.Username, Password: initial.Credentials.Password},
		ctx: context.Background(), progress: func(float64) {}, executionTimeout: time.Duration(seconds) * time.Second, jobs: map[string]Job{}, papers: map[string]*paper{}, assessmentsByID: map[string]assessmentTarget{}}
	cookies := []*http.Cookie{}
	for _, c := range initial.Cookies {
		if !allowedHost(strings.TrimPrefix(c.Domain, ".")) || c.Name == "" || len(c.Value) > 16000 {
			continue
		}
		cookie := &http.Cookie{Name: c.Name, Value: c.Value, Domain: c.Domain, Path: c.Path, Secure: c.Secure}
		if c.Expires != nil {
			cookie.Expires = time.Unix(*c.Expires, 0)
		}
		cookies = append(cookies, cookie)
	}
	r.cache.SetCookies(cookies)
	r.mediaClient = initial.Credentials.MediaClient
	r.proxyURL = initial.Credentials.ProxyURL
	r.cache.UserID = cookieUserID(cookies)
	r.now = time.Now
	r.wait = func(duration time.Duration) error {
		timer := time.NewTimer(duration)
		defer timer.Stop()
		select {
		case <-timer.C:
			return nil
		case <-r.ctx.Done():
			return r.ctx.Err()
		}
	}
	yatori.ConsoleRequestHook = r.request
	return r, nil
}

func (r *Runtime) Dispatch(operation string, raw json.RawMessage) (data any, err error) {
	defer func() {
		if recover() != nil {
			data = nil
			err = failure("parser_changed")
		}
		if r.lastFailure != nil {
			data = nil
			err = r.lastFailure
		}
	}()
	r.lastFailure = nil
	r.currentCard = nil
	yatori.ConsoleRequestHook = r.request
	var args struct {
		Username        string              `json:"username"`
		Password        string              `json:"password"`
		Course          Course              `json:"course"`
		Chapter         Chapter             `json:"chapter"`
		Job             Job                 `json:"job"`
		Work            bool                `json:"work"`
		Exam            bool                `json:"exam"`
		Assessment      Assessment          `json:"assessment"`
		PaperID         string              `json:"paper_id"`
		Answers         map[string][]string `json:"answers"`
		Submit          bool                `json:"submit"`
		RequireComplete bool                `json:"require_complete"`
		Question        PaperQuestion       `json:"question"`
	}
	if len(raw) > 0 && string(raw) != "null" && json.Unmarshal(raw, &args) != nil {
		return nil, failure("adapter_error")
	}
	switch operation {
	case "login":
		return nil, r.login(args.Username, args.Password)
	case "list_courses":
		return r.courses()
	case "list_chapters":
		return r.chapters(args.Course)
	case "list_jobs":
		return r.listJobs(args.Course, args.Chapter)
	case "execute":
		return nil, r.execute(args.Course, args.Job)
	case "questions":
		return r.questions(args.Course, args.Job)
	case "list_assessments":
		return r.assessments(args.Course, args.Work, args.Exam)
	case "assessment_questions":
		return r.openAssessment(args.Course, args.Assessment)
	case "chapter_paper":
		return r.chapterPaper(args.Course, args.Job)
	case "save_answers":
		return r.saveAnswers(args.PaperID, args.Answers, args.Submit, args.RequireComplete)
	case "chaoxing_answer":
		return r.chaoxingAnswer(args.Course, args.Question)
	case "export_cookies":
		cookies := []Cookie{}
		for _, c := range r.cache.GetCookies() {
			if !allowedHost(strings.TrimPrefix(c.Domain, ".")) {
				continue
			}
			item := Cookie{Name: c.Name, Value: c.Value, Domain: c.Domain, Path: c.Path, Secure: c.Secure}
			if !c.Expires.IsZero() {
				value := c.Expires.Unix()
				item.Expires = &value
			}
			cookies = append(cookies, item)
		}
		return cookies, nil
	default:
		return nil, failure("adapter_error")
	}
}

func (r *Runtime) coreError(err error) error {
	if r.lastFailure != nil {
		return r.lastFailure
	}
	if err != nil {
		return err
	}
	return failure("parser_changed")
}
func text(value any) string {
	switch v := value.(type) {
	case string:
		return v
	case float64:
		return strconv.FormatInt(int64(v), 10)
	case json.Number:
		return string(v)
	case int:
		return strconv.Itoa(v)
	default:
		return ""
	}
}
func number(value any) int { n, _ := strconv.Atoi(text(value)); return n }
func count(value any) (int, bool) {
	n, err := strconv.Atoi(fmt.Sprint(value))
	return n, err == nil && n >= 0
}
func field(value map[string]any, key string) string { return text(value[key]) }
func object(value any) map[string]any               { data, _ := value.(map[string]any); return data }
func array(value any) []any                         { data, _ := value.([]any); return data }
func parseObject(raw string) (map[string]any, error) {
	var d map[string]any
	if json.Unmarshal([]byte(raw), &d) != nil || d == nil {
		return nil, failure("parser_changed")
	}
	return d, nil
}

func cookieUserID(cookies []*http.Cookie) string {
	fallback := ""
	for _, cookie := range cookies {
		if cookie.Name == "_uid" && cookie.Value != "" {
			return cookie.Value
		}
		if cookie.Name == "UID" {
			fallback = cookie.Value
		}
	}
	return fallback
}

func (r *Runtime) login(username, password string) error {
	r.cache.Name, r.cache.Password = username, password
	raw, err := r.cache.LoginApi(0)
	if err != nil {
		return r.coreError(err)
	}
	data, err := parseObject(raw)
	if err != nil {
		return err
	}
	if data["status"] != true {
		return failure("login_failed")
	}
	r.cache.UserID = cookieUserID(r.cache.GetCookies())
	if r.cache.UserID == "" {
		r.cache.UserID = field(data, "uid")
	}
	if r.cache.UserID == "" {
		return failure("parser_changed")
	}
	return nil
}
