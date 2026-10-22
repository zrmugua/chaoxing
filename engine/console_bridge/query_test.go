//go:build consolebridge

package main

import (
	"errors"
	"reflect"
	"strconv"
	"strings"
	"testing"

	core "github.com/yatori-dev/yatori-go-core/aggregation/xuexitong"
	api "github.com/yatori-dev/yatori-go-core/api/xuexitong"
	"yatori-go-console/config"
	consolexxt "yatori-go-console/logic/xuexitong"
)

func freshQuerySession(t *testing.T) *api.XueXiTUserCache {
	t.Helper()
	// Exercise Console's cookie-login path using an isolated synthetic account.
	caches := consolexxt.UserLoginOperation([]config.User{{AccountType: "XUEXITONG",
		Account: "query-fixture", Password: "fixture=" + strings.Repeat("x", 60)}})
	if len(caches) != 1 || caches[0].UserID != "" {
		t.Fatal("expected a fresh logged-in session awaiting course initialization")
	}
	return caches[0]
}

func queryFixture(t *testing.T, calls *[]string) (core.XueXiTCourse, bridgeCourseActions) {
	t.Helper()
	requested := core.XueXiTCourse{CourseID: "201", Key: "301", Cpi: 1}
	current := requested
	current.Cpi = 401
	assertCurrent := func(cache *api.XueXiTUserCache, course core.XueXiTCourse) {
		t.Helper()
		if cache.UserID != "501" || course != current {
			t.Fatalf("query used an uninitialized session or stale course: uid=%q course=%+v", cache.UserID, course)
		}
	}
	return requested, bridgeCourseActions{
		courses: func(cache *api.XueXiTUserCache) ([]core.XueXiTCourse, error) {
			*calls = append(*calls, "courses")
			cache.UserID = "501" // Contract of the original XueXiTPullCourseAction.
			return []core.XueXiTCourse{
				{CourseID: "201", Key: "302", Cpi: 402},
				{CourseID: "202", Key: "301", Cpi: 403}, current,
			}, nil
		},
		chapters: func(cache *api.XueXiTUserCache, cpi, classID int) (core.ChaptersList, bool, error) {
			*calls = append(*calls, "chapters")
			assertCurrent(cache, core.XueXiTCourse{CourseID: "201", Key: strconv.Itoa(classID), Cpi: cpi})
			return core.ChaptersList{Knowledge: []core.KnowledgeItem{{ID: 101, Name: "Fixture chapter"}}}, true, nil
		},
		points: func(cache *api.XueXiTUserCache, nodes []int, classID, userID, cpi, courseID, retry int, lastErr error) (string, error) {
			*calls = append(*calls, "points")
			assertCurrent(cache, core.XueXiTCourse{CourseID: strconv.Itoa(courseID), Key: strconv.Itoa(classID), Cpi: cpi})
			if userID != 501 || !reflect.DeepEqual(nodes, []int{101}) {
				t.Fatalf("incorrect chapter request: userID=%d nodes=%v", userID, nodes)
			}
			return `{"msg":"成功","101":{"totalcount":2,"finishcount":2,"unfinishcount":0}}`, nil
		},
		works: func(cache *api.XueXiTUserCache, course core.XueXiTCourse) ([]core.XXTWork, error) {
			*calls = append(*calls, "works")
			assertCurrent(cache, course)
			return []core.XXTWork{{Name: "Fixture work", TaskRefId: "601"}}, nil
		},
		exams: func(cache *api.XueXiTUserCache, course core.XueXiTCourse) ([]core.XXTExam, error) {
			*calls = append(*calls, "exams")
			assertCurrent(cache, course)
			return []core.XXTExam{{Name: "Fixture exam", TaskRefId: "701"}}, nil
		},
	}
}

func TestFreshLoginChapterQueryInitializesIdentity(t *testing.T) {
	// Each UI refresh starts a new process, so a previous course sync cannot
	// supply the next query's in-memory account identity.
	for attempt := 0; attempt < 2; attempt++ {
		var calls []string
		requested, actions := queryFixture(t, &calls)
		result, err := bridgeAccountQuery("chapters", freshQuerySession(t), requested, actions)
		if err != nil {
			t.Fatal(err)
		}
		rows := result.([]map[string]any)
		if len(rows) != 1 || rows[0]["id"] != "101" || rows[0]["has_finished"] != true || rows[0]["jobCount"] != 2 {
			t.Fatalf("unexpected progress: %v", result)
		}
		if !reflect.DeepEqual(calls, []string{"courses", "chapters", "points"}) {
			t.Fatalf("query sequence: %v", calls)
		}
	}
}

func TestAssessmentQueryUsesCurrentCourseSession(t *testing.T) {
	var calls []string
	requested, actions := queryFixture(t, &calls)
	result, err := bridgeAccountQuery("assessments", freshQuerySession(t), requested, actions)
	if err != nil || len(result.([]map[string]any)) != 2 || !reflect.DeepEqual(calls, []string{"courses", "works", "exams"}) {
		t.Fatalf("assessment query: %v %v calls=%v", result, err, calls)
	}
}

func TestCourseListQueryStopsAfterListing(t *testing.T) {
	var calls []string
	_, actions := queryFixture(t, &calls)
	result, err := bridgeAccountQuery("courses", freshQuerySession(t), core.XueXiTCourse{}, actions)
	if err != nil || len(result.([]map[string]any)) != 3 || !reflect.DeepEqual(calls, []string{"courses"}) {
		t.Fatalf("course listing: %v %v calls=%v", result, err, calls)
	}
}

func TestCourseInitializationFailureStopsQuery(t *testing.T) {
	for _, mode := range []string{"chapters", "assessments"} {
		for _, failure := range []string{"list-error", "missing-course", "wrong-class"} {
			t.Run(mode+"/"+failure, func(t *testing.T) {
				var calls []string
				requested, actions := queryFixture(t, &calls)
				listError := errors.New("课程列表暂时不可用")
				actions.courses = func(cache *api.XueXiTUserCache) ([]core.XueXiTCourse, error) {
					calls = append(calls, "courses")
					if failure == "list-error" {
						return nil, listError
					}
					if failure == "wrong-class" {
						return []core.XueXiTCourse{{CourseID: requested.CourseID, Key: "302"}}, nil
					}
					return nil, nil
				}
				result, err := bridgeAccountQuery(mode, freshQuerySession(t), requested, actions)
				if err == nil || result != nil || !reflect.DeepEqual(calls, []string{"courses"}) {
					t.Fatalf("query continued after initialization failure: %v %v calls=%v", result, err, calls)
				}
				if failure == "list-error" && !errors.Is(err, listError) {
					t.Fatal("course-list error was lost")
				}
			})
		}
	}
}

func TestInvalidSessionIdentityStopsBeforeChapters(t *testing.T) {
	for _, id := range []string{"", "0", "invalid", "99999999999999999999999999"} {
		var calls []string
		requested, actions := queryFixture(t, &calls)
		load := actions.courses
		actions.courses = func(cache *api.XueXiTUserCache) ([]core.XueXiTCourse, error) {
			courses, err := load(cache)
			cache.UserID = id
			return courses, err
		}
		result, err := bridgeAccountQuery("chapters", freshQuerySession(t), requested, actions)
		if result != nil || err == nil || !strings.Contains(err.Error(), "账号编号") || !reflect.DeepEqual(calls, []string{"courses"}) {
			t.Fatalf("invalid session: %v %v calls=%v", result, err, calls)
		}
	}
}

func TestQueryIdentityDiagnostics(t *testing.T) {
	for _, test := range []struct{ value, want string }{
		{"", "未返回"}, {" ", "未返回"}, {"0", "格式无效"}, {"-1", "格式无效"},
		{"invalid", "格式无效"}, {"99999999999999999999999999", "整数范围"},
	} {
		id, err := bridgePositiveID(test.value, "账号")
		if id != 0 || err == nil || !strings.Contains(err.Error(), test.want) {
			t.Fatalf("identity error: id=%d err=%v", id, err)
		}
	}
	id, err := bridgePositiveID("2147483648", "课程")
	if strconv.IntSize == 32 {
		if err == nil || !strings.Contains(err.Error(), "32 位") {
			t.Fatalf("expected 32-bit overflow: %v", err)
		}
	} else if err != nil || int64(id) != 2147483648 {
		t.Fatalf("valid 64-bit identity: %d %v", id, err)
	}
}
