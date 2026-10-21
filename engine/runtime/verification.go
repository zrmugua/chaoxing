package runtime

import (
	"errors"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

type manualRequirement struct{ reason string }

func (e *manualRequirement) Error() string { return "manual_required" }

func requireManual(reason string) error { return &manualRequirement{reason: reason} }

func manualReason(err error) string {
	var requirement *manualRequirement
	if errors.As(err, &requirement) {
		return requirement.reason
	}
	return ""
}

// Inspect page markup after excluding scripts and explicitly hidden elements.
func verificationDocument(page string) (*goquery.Document, error) {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(page))
	if err != nil {
		return nil, failure("parser_changed")
	}
	doc.Find("script, style, template, noscript, [hidden], [aria-hidden='true'], .hidden, .hide").Remove()
	doc.Find("[style]").Each(func(_ int, node *goquery.Selection) {
		style, _ := node.Attr("style")
		style = strings.NewReplacer(" ", "", "\t", "", "\n", "", "\r", "").Replace(strings.ToLower(style))
		if strings.Contains(style, "display:none") || strings.Contains(style, "visibility:hidden") {
			node.Remove()
		}
	})
	return doc, nil
}

func pageVerification(doc *goquery.Document, paper bool) error {
	fields := hiddenFields(doc)
	for _, flag := range []struct{ key, reason string }{{"needface", "face"}, {"needcaptcha", "captcha"}, {"needverify", "verification"}} {
		value := strings.ToLower(strings.TrimSpace(fields[flag.key]))
		if value != "" && value != "0" && value != "false" {
			return requireManual(flag.reason)
		}
	}
	hasQuestions := doc.Find(".Py-mian1 .workTextWrap, .singleQuesId .workWrap").Length() > 0
	var challenge error
	doc.Find("input").Each(func(_ int, input *goquery.Selection) {
		typ, _ := input.Attr("type")
		id, _ := input.Attr("id")
		name, _ := input.Attr("name")
		key := strings.ToLower(id + " " + name)
		if !strings.EqualFold(typ, "hidden") && !strings.Contains(key, "captchacaptchaid") && (strings.Contains(key, "captcha") || strings.Contains(key, "verifycode")) {
			challenge = requireManual("captcha")
		}
	})
	if challenge != nil {
		return challenge
	}
	if !hasQuestions && fields["captchacaptchaid"] != "" && fields["captchacaptchaid"] != "0" {
		return requireManual("captcha")
	}
	text := doc.Clone()
	text.Find(".Py-mian1, .singleQuesId, input").Remove()
	visible := text.Text()
	for _, marker := range []struct{ text, reason string }{
		{"请输入验证码", "captcha"}, {"请输入图片中的验证码", "captcha"}, {"人机验证", "verification"},
		{"请先完成人脸识别", "face"}, {"需要人脸识别", "face"}, {"请进行人脸识别", "face"},
		{"访问过于频繁", "rate_limit"}, {"很抱歉，您所浏览的页面暂时不能访问", "access_restricted"},
	} {
		if strings.Contains(visible, marker.text) {
			return requireManual(marker.reason)
		}
	}
	if !hasQuestions {
		for _, marker := range []struct{ text, reason string }{{"安全验证", "verification"}, {"人脸识别", "face"}} {
			if strings.Contains(visible, marker.text) {
				return requireManual(marker.reason)
			}
		}
	}
	if paper {
		for _, marker := range []struct{ text, reason string }{{"已截止，不能作答", "paper_closed"}, {"已过时效", "paper_closed"}, {"待重考", "paper_retake"}, {"待重做", "paper_retake"}} {
			if strings.Contains(visible, marker.text) {
				return requireManual(marker.reason)
			}
		}
		if !hasQuestions && strings.Contains(visible, "考试须知") {
			return requireManual("paper_notice")
		}
	}
	return nil
}
