package runtime

import (
	"sort"
	"strconv"
)

func (r *Runtime) courses() ([]Course, error) {
	raw, err := r.cache.CourseListApiContext(r.ctx, 0, nil)
	if err != nil {
		return nil, r.coreError(err)
	}
	data, err := parseObject(raw)
	if err != nil {
		return nil, err
	}
	channels, ok := data["channelList"].([]any)
	if !ok {
		return nil, failure("parser_changed")
	}
	result := []Course{}
	seen := map[string]bool{}
	for _, item := range channels {
		channel := object(item)
		content := object(channel["content"])
		for _, entry := range array(object(content["course"])["data"]) {
			course := object(entry)
			id, clazz, cpi := field(course, "id"), field(content, "id"), field(channel, "cpi")
			if cpi == "" {
				cpi = field(content, "cpi")
			}
			if id == "" || clazz == "" || cpi == "" {
				return nil, failure("parser_changed")
			}
			key := id + ":" + clazz + ":" + cpi
			if seen[key] {
				continue
			}
			seen[key] = true
			result = append(result, Course{"courseId": id, "clazzId": clazz, "cpi": cpi, "title": field(course, "name"), "teacher": field(course, "teacherfactor")})
		}
	}
	return result, nil
}

func (r *Runtime) chapters(course Course) ([]Chapter, error) {
	raw, err := r.cache.PullChapterContext(r.ctx, number(course["cpi"]), number(course["clazzId"]), 0, nil)
	if err != nil {
		return nil, r.coreError(err)
	}
	data, err := parseObject(raw)
	if err != nil {
		return nil, err
	}
	rows := array(data["data"])
	if len(rows) == 0 {
		return nil, failure("parser_changed")
	}
	courses := array(object(object(rows[0])["course"])["data"])
	if len(courses) == 0 {
		return nil, failure("parser_changed")
	}
	knowledge, ok := object(object(courses[0])["knowledge"])["data"].([]any)
	if !ok {
		return nil, failure("parser_changed")
	}
	result := []Chapter{}
	nodes := []int{}
	parents := map[string]bool{}
	for _, entry := range knowledge {
		node := object(entry)
		if id := field(node, "parentnodeid"); id != "" && id != "0" {
			parents[id] = true
		}
	}
	for _, entry := range knowledge {
		node := object(entry)
		id := field(node, "id")
		if id == "" {
			return nil, failure("parser_changed")
		}
		jobCount, knownCount := count(node["jobcount"])
		if parents[id] && knownCount && jobCount == 0 {
			continue
		}
		result = append(result, Chapter{ID: id, Title: field(node, "name"), JobCount: number(node["jobcount"]), Locked: field(node, "status") == "locked"})
		r.chapterTitles[id] = field(node, "name")
		nodes = append(nodes, number(node["id"]))
	}
	// The chapter-status endpoint is authoritative; missing nodes stay unknown.
	for start := 0; start < len(nodes); start += 100 {
		end := start + 100
		if end > len(nodes) {
			end = len(nodes)
		}
		statusRaw, err := r.cache.FetchChapterPointStatusContext(r.ctx, nodes[start:end], number(course["clazzId"]), number(r.cache.UserID), number(course["cpi"]), number(course["courseId"]), 0, nil)
		if err != nil {
			return nil, r.coreError(err)
		}
		statuses, err := parseObject(statusRaw)
		if err != nil {
			return nil, err
		}
		for i := start; i < end; i++ {
			state := object(statuses[result[i].ID])
			if state == nil {
				continue
			}
			total, totalOK := state["totalcount"]
			unfinished, unfinishedOK := state["unfinishcount"]
			finished, finishedOK := state["finishcount"]
			totalCount, validTotal := count(total)
			unfinishedCount, validUnfinished := count(unfinished)
			finishedCount, validFinished := count(finished)
			result[i].Finished = totalOK && unfinishedOK && finishedOK && validTotal && validUnfinished && validFinished && totalCount > 0 && unfinishedCount == 0 && finishedCount >= totalCount
		}
	}
	// API index order is used when labels are absent.
	order := map[string]int{}
	for _, entry := range knowledge {
		node := object(entry)
		order[field(node, "id")] = number(node["indexorder"])
	}
	sort.SliceStable(result, func(i, j int) bool { return order[result[i].ID] < order[result[j].ID] })
	r.consoleRunner(course, "").Log("", "获取课程章节成功 (共 ", strconv.Itoa(len(result)), " 个)")
	return result, nil
}

func courseInt(course Course, key string) (int, error) {
	n, err := strconv.Atoi(field(course, key))
	if err != nil || n <= 0 {
		return 0, failure("parser_changed")
	}
	return n, nil
}
