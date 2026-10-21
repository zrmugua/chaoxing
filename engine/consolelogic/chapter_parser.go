// SPDX-License-Identifier: MIT
// Copyright (c) 2023 ChangBaiQi
// Adapted from yatori-go-core aggregation/xuexitong/XueXiTongCardAction.go.
// The Console caller supplies the verified page; parsing retains upstream DTOs.
package consolelogic

import (
	"bytes"
	"errors"
	"fmt"
	"github.com/PuerkitoBio/goquery"
	"github.com/yatori-dev/yatori-go-core/api/xuexitong"
	"github.com/yatori-dev/yatori-go-core/que-core/qtype"
	"github.com/yatori-dev/yatori-go-core/utils"
	log2 "github.com/yatori-dev/yatori-go-core/utils/log"
	"golang.org/x/net/html"
	"regexp"
	"strings"
)

func cleanText(text string) string {
	text = strings.TrimSpace(text)
	text = regexp.MustCompile(`\n+`).ReplaceAllString(text, " ")

	return regexp.MustCompile(`\s+`).ReplaceAllString(text, " ")
}

func WorkInformInputWorkDTO(informMap map[string]interface{}, question *xuexitong.Question) {
	if v, ok := informMap["title"]; ok {
		question.Title = v.(string)
	}
	if v, ok := informMap["jobid"]; ok {
		question.JobId = v.(string)
	}
	if v, ok := informMap["cpi"]; ok {
		question.Cpi = v.(string)
	}
	if v, ok := informMap["knowledgeid"]; ok {
		question.Knowledgeid = v.(string)
	}
	if v, ok := informMap["userId"]; ok {
		question.UserId = v.(string)
	}
	if v, ok := informMap["workAnswerId"]; ok {
		question.WorkAnswerId = v.(string)
	}
	if v, ok := informMap["answerId"]; ok {
		question.AnswerId = v.(string)
	}
	if v, ok := informMap["totalQuestionNum"]; ok {
		question.TotalQuestionNum = v.(string)
	}
	if v, ok := informMap["workRelationId"]; ok {
		question.WorkRelationId = v.(string)
	}
	if v, ok := informMap["oldSchoolId"]; ok {
		question.OldSchoolId = v.(string)
	}
	if v, ok := informMap["oldWorkId"]; ok {
		question.OldWorkId = v.(string)
	}
	if v, ok := informMap["enc_work"]; ok {
		question.Enc_work = v.(string)
	}
	if v, ok := informMap["fullScore"]; ok {
		question.FullScore = v.(string)
	}
	if v, ok := informMap["api"]; ok {
		question.Api = v.(string)
	}
	if v, ok := informMap["courseId"]; ok {
		question.CourseId = v.(string)
	}
	if v, ok := informMap["classId"]; ok {
		question.ClassId = v.(string)
	}
	if v, ok := informMap["randomOptions"]; ok {
		question.RandomOptions = v.(string)
	}
}

func ParseWorkQuestionPage(cache *xuexitong.XueXiTUserCache, page string) (xuexitong.Question, error) {
	var questionEntity xuexitong.Question
	var workQuestion []xuexitong.ChoiceQue
	var judgeQuestion []xuexitong.JudgeQue
	var fillQuestion []xuexitong.FillQue
	var shortQuestion []xuexitong.ShortQue
	var termQuestion []xuexitong.TermExplanationQue
	var essayQuestion []xuexitong.EssayQue
	var matchingQuestion []xuexitong.MatchingQue
	var otherQuestion []xuexitong.OtherQue
	doc, err := goquery.NewDocumentFromReader(bytes.NewReader([]byte(page)))
	if err != nil {
		return questionEntity, fmt.Errorf("解析作业页面失败: %w", err)
	}

	informMap, err := utils.ParseWorkInform(doc)
	WorkInformInputWorkDTO(informMap, &questionEntity) //转换

	textStatus := doc.Find("div.chapter-content").Text()
	if strings.Contains(textStatus, "已截止，不能作答") {
		return questionEntity, errors.New("已截止，不能作答")
	}

	var extractQuestionType = func(text string) string {
		start := strings.Index(text, "[")
		end := strings.Index(text, "]")

		if start != -1 && end != -1 && end > start {
			content := text[start+1 : end]
			return strings.TrimSpace(content)
		}
		return ""
	}

	questionSets := utils.ParseQuestionSets(doc)
	for _, qs := range questionSets {
		qdoc, err := goquery.NewDocumentFromReader(bytes.NewReader([]byte(qs.HTML)))
		if err != nil {
			return questionEntity, fmt.Errorf("解析作业题目失败: %w", err)
		}

		quesType := qdoc.Find(".Py-m1-title .quesType").Text()
		quesType = extractQuestionType(quesType)
		if strings.Contains(quesType, "辨析题") {
			quesType = "判断题" //将辨析题当判断题进行
		} else if strings.Contains(quesType, "投票题") {
			quesType = "单选题"
		}

		var quesTextBuilder strings.Builder //文本题目
		quesText := qdoc.Find(".Py-m1-title .workTextWrap").Contents().Each(func(i int, n *goquery.Selection) {
			if n.Get(0).Type == html.ElementNode || n.Get(0).Type == html.TextNode && n.Text() != "" {
				quesTextBuilder.WriteString(n.Text())
			}
		}).End().Text()

		quesText = cleanText(quesTextBuilder.String())

		switch quesType {
		case qtype.SingleChoice.String():
			options := make(map[string]string)
			choiceQue := xuexitong.ChoiceQue{}
			choiceQue.Type = qtype.SingleChoice
			choiceQue.Qid = qs.ID
			choiceQue.Text = quesText
			resOptions := make(map[string]string)
			qdoc.Find(".answerList li").Each(func(i int, s *goquery.Selection) {
				optionLetter := s.Find("em.choose-opt").Text()
				trueOptionLetter, _ := s.Find("em.choose-opt").Attr("id-param") //如果这个不是空的说明这个才是正确的选项参数
				if trueOptionLetter != "" {
					optionLetter = trueOptionLetter
				}
				ccContent := s.Find("cc").Contents().First()
				text := ccContent.Text()
				if text == "" {
					text = s.Find("cc").Contents().Text()
				}
				if text == "" {
					img, exists := s.Find("cc img").Attr("src")
					if exists {
						text = "Image: " + img
					} else {
						text = "No content available"
					}
				}
				resOptions[optionLetter] = text
			})
			resSelect := []string{"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"}
			for _, sel := range resSelect {
				if resOptions[sel] == "" {
					break
				}
				options[sel] = resOptions[sel]
			}
			choiceQue.Options = options
			workQuestion = append(workQuestion, choiceQue)
			break
		case qtype.MultipleChoice.String():
			options := make(map[string]string)
			choiceQue := xuexitong.ChoiceQue{}
			choiceQue.Type = qtype.MultipleChoice
			choiceQue.Qid = qs.ID
			choiceQue.Text = quesText
			resOptions := make(map[string]string)
			qdoc.Find(".answerList li").Each(func(i int, s *goquery.Selection) {
				optionLetter := s.Find("em.choose-opt").Text()
				trueOptionLetter, _ := s.Find("em.choose-opt").Attr("id-param") //如果这个不是空的说明这个才是正确的选项参数
				if trueOptionLetter != "" {
					optionLetter = trueOptionLetter
				}
				ccContent := s.Find("cc").Contents().First()
				text := ccContent.Text()

				if text == "" {
					text = s.Find("cc").Contents().Text()
				}
				if text == "" {
					img, exists := s.Find("cc img").Attr("src")
					if exists {
						text = "Image: " + img
					} else {
						text = "No content available"
					}
				}
				resOptions[optionLetter] = text
			})
			resSelect := []string{"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"}
			for _, sel := range resSelect {
				if resOptions[sel] == "" {
					break
				}
				options[sel] = resOptions[sel]
			}
			choiceQue.Options = options
			workQuestion = append(workQuestion, choiceQue)
			break
		case qtype.TrueOrFalse.String():
			options := make(map[string]string)
			judgeQue := xuexitong.JudgeQue{}
			judgeQue.Type = qtype.TrueOrFalse
			judgeQue.Qid = qs.ID
			judgeQue.Text = quesText
			qdoc.Find(".answerList.panduan li").Each(func(i int, s *goquery.Selection) {
				optionLetter := s.Find("em").Text()
				trueoption, _ := s.Attr("val-param")
				if trueoption == "true" {
					optionLetter = "对"
				} else if trueoption == "false" {
					optionLetter = "错"
				}

				ccContent := s.Find("p").Contents().First()
				text := ccContent.Text()

				options[optionLetter] = text
			})
			judgeQue.Options = options
			judgeQuestion = append(judgeQuestion, judgeQue)
		case qtype.FillInTheBlank.String():
			options := []string{}
			fillQue := xuexitong.FillQue{}
			fillQue.Type = qtype.FillInTheBlank
			fillQue.Qid = qs.ID
			fillQue.Text = quesText
			qdoc.Find("ul.blankList2").Each(func(i int, selection *goquery.Selection) {
				optionLetter := selection.Find("p").Text()
				splitOptions := strings.Split(optionLetter, ":")
				validParts := splitOptions[:0]
				for _, part := range splitOptions {
					if part != "" { // 忽略空值
						validParts = append(validParts, part)
					}
				}
				for j, _ := range validParts {
					options = append(options, fmt.Sprintf("%d", j+1))
				}
			})
			fillQue.OpFromAnswer = options
			fillQuestion = append(fillQuestion, fillQue)
		case qtype.ShortAnswer.String():
			options := make(map[string][]string)
			shortQue := xuexitong.ShortQue{}
			shortQue.Type = qtype.ShortAnswer
			shortQue.Qid = qs.ID
			shortQue.Text = quesText
			options["简答"] = []string{"简答答案"}
			shortQue.OpFromAnswer = options
			shortQuestion = append(shortQuestion, shortQue)
		case qtype.TermExplanation.String(): //名词解释
			options := make(map[string][]string)
			termExplanationQue := xuexitong.TermExplanationQue{}
			termExplanationQue.Type = qtype.TermExplanation
			termExplanationQue.Qid = qs.ID
			termExplanationQue.Text = quesText
			options["名词解释"] = []string{"名词解释"}
			termExplanationQue.OpFromAnswer = options
			termQuestion = append(termQuestion, termExplanationQue)
		case qtype.Essay.String(): //论述题
			options := make(map[string][]string)
			essayQue := xuexitong.EssayQue{}
			essayQue.Type = qtype.Essay
			essayQue.Qid = qs.ID
			essayQue.Text = quesText
			options["论述"] = []string{"论述"}
			essayQue.OpFromAnswer = options
			essayQuestion = append(essayQuestion, essayQue)
		case qtype.Matching.String():

			matchingQue := xuexitong.MatchingQue{}
			matchingQue.Qid = qs.ID
			matchingQue.Type = qtype.Matching
			matchingQue.Text = quesText
			options := []string{}
			selects := []string{}
			qdoc.Find("ul.answerList-line").Each(func(i int, s *goquery.Selection) {
				if i%2 == 0 {
					s.Find("li").Each(func(_ int, li *goquery.Selection) {
						options = append(options, li.Text())
					})
				} else {
					s.Find("li").Each(func(_ int, li *goquery.Selection) {
						selects = append(selects, li.Text())
					})
				}
			})
			matchingQue.Options = options
			matchingQue.Selects = selects
			matchingQuestion = append(matchingQuestion, matchingQue)
		case qtype.QueOther.String():
			options := make(map[string][]string)
			otherQue := xuexitong.OtherQue{}
			otherQue.Type = qtype.QueOther
			otherQue.Qid = qs.ID
			otherQue.Text = quesText
			options["回复"] = []string{""}
			otherQue.OpFromAnswer = options
			otherQuestion = append(otherQuestion, otherQue)
		case qtype.ReadingComprehension.String(): //阅读理解题处理(未完工）
			doc.Find("ul.answerList").Each(func(i int, s *goquery.Selection) {
				queType := s.Find("li.ignoreli .span").Text() //截取题目类型
				if strings.Contains(queType, "单选题") {
					content := strings.TrimSpace(doc.Find(".ans-cc p").Text())
					fmt.Println(content)
					doc.Find(`li[data="answer"]`).Each(func(i int, s *goquery.Selection) {
						option := strings.TrimSpace(s.Find("em").Text())
						selectContent := strings.TrimSpace(s.Find("cc p").Text())
						fmt.Printf("选项 %s: %s\n", option, selectContent)
					})
				}
			})
		case qtype.JournalEntry.String(): //分录题，暂时按照填空题处理
			options := []string{}
			fillQue := xuexitong.FillQue{}
			fillQue.Type = qtype.FillInTheBlank
			fillQue.Qid = qs.ID
			fillQue.Text = quesText
			qdoc.Find("ul").Each(func(i int, selection *goquery.Selection) {
				optionLetter := selection.Find("p").Text()
				splitOptions := strings.Split(optionLetter, ":")
				validParts := splitOptions[:0]
				for _, part := range splitOptions {
					if part != "" { // 忽略空值
						validParts = append(validParts, part)
					}
				}
				for j, _ := range validParts {
					options = append(options, fmt.Sprintf("%d", j+1))
				}
			})
			fillQue.OpFromAnswer = options
			fillQuestion = append(fillQuestion, fillQue)
		default:
			log2.Print(log2.INFO, "[", cache.Name, "] ", "未知题目类型，类型为：", quesType, "默认采用论述题方式")
			options := make(map[string][]string)
			essayQue := xuexitong.EssayQue{}
			essayQue.Type = qtype.Essay
			essayQue.Qid = qs.ID
			essayQue.Text = quesText
			options["论述"] = []string{"论述"}
			essayQue.OpFromAnswer = options
			essayQuestion = append(essayQuestion, essayQue)
		}
	}

	questionEntity.Choice = workQuestion
	questionEntity.Judge = judgeQuestion
	questionEntity.Fill = fillQuestion
	questionEntity.Short = shortQuestion
	questionEntity.TermExplanation = termQuestion
	questionEntity.Essay = essayQuestion
	questionEntity.Matching = matchingQuestion
	questionEntity.Other = otherQuestion
	return questionEntity, nil
}
