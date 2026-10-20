package runtime

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

func allowedHost(host string) bool {
	return host == "chaoxing.com" || strings.HasSuffix(host, ".chaoxing.com")
}
func validateURL(value *url.URL) error {
	if value.Scheme != "https" || value.User != nil || (value.Port() != "" && value.Port() != "443") || !allowedHost(strings.ToLower(value.Hostname())) {
		return failure("blocked_destination")
	}
	path := strings.ToLower(value.Path)
	for _, marker := range []string{"processverify", "captcha", "/face/", "/faceid/", "/facephoto"} {
		if strings.Contains(path, marker) {
			return failure("manual_required")
		}
	}
	return nil
}

type guardedTransport struct {
	owner *Runtime
	base  http.RoundTripper
}

func (g guardedTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	if err := validateURL(request.URL); err != nil {
		return nil, err
	}
	response, err := g.base.RoundTrip(request)
	if err != nil {
		return nil, err
	}
	if response.StatusCode >= 300 && response.StatusCode < 400 {
		if location := response.Header.Get("Location"); location != "" {
			target, parseErr := request.URL.Parse(location)
			if parseErr != nil {
				response.Body.Close()
				return nil, failure("blocked_destination")
			}
			if err := validateURL(target); err != nil {
				response.Body.Close()
				return nil, err
			}
			if target.Hostname() == "passport2.chaoxing.com" && strings.Contains(target.Path, "login") {
				response.Body.Close()
				return nil, failure("session_expired")
			}
		}
		return response, nil
	}
	body, readErr := io.ReadAll(io.LimitReader(response.Body, 2_000_001))
	response.Body.Close()
	if readErr != nil {
		return nil, readErr
	}
	if len(body) > 2_000_000 {
		return nil, failure("parser_changed")
	}
	lower := strings.ToLower(string(body))
	for _, marker := range []string{"请输入验证码", "请输入图片中的验证码", "人机验证", "安全验证", "访问过于频繁", "很抱歉，您所浏览的页面暂时不能访问", `title : "人脸识别"`, `id="captcha"`} {
		if strings.Contains(lower, marker) {
			return nil, failure("manual_required")
		}
	}
	if response.StatusCode == 403 || response.StatusCode == 429 || response.StatusCode == 202 {
		return nil, failure("manual_required")
	}
	if response.StatusCode == 401 || (strings.Contains(lower, "<form") && strings.Contains(lower, `name="password"`)) {
		return nil, failure("session_expired")
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, failure("remote_error")
	}
	var challenge map[string]any
	if json.Unmarshal(body, &challenge) == nil {
		for _, key := range []string{"needFace", "needCaptcha", "needVerify"} {
			if challenge[key] == true || challenge[key] == float64(1) {
				return nil, failure("manual_required")
			}
		}
	}
	// Normalize host-only cookies before the upstream cache exports them.
	cookieValues := response.Cookies()
	if len(cookieValues) > 0 {
		response.Header.Del("Set-Cookie")
		for _, cookie := range cookieValues {
			if cookie.Domain == "" {
				cookie.Domain = request.URL.Hostname()
			}
			if cookie.Path == "" {
				cookie.Path = "/"
			}
			response.Header.Add("Set-Cookie", cookie.String())
		}
	}
	response.Body = io.NopCloser(bytes.NewReader(body))
	return response, nil
}

func (r *Runtime) request(client *http.Client, request *http.Request) (*http.Response, error) {
	if err := validateURL(request.URL); err != nil {
		r.lastFailure = err
		return nil, err
	}
	base := r.transport
	if base == nil {
		tr := http.DefaultTransport.(*http.Transport).Clone()
		tr.Proxy = nil
		if r.proxyURL != "" {
			proxy, err := url.Parse(r.proxyURL)
			if err != nil || (proxy.Scheme != "http" && proxy.Scheme != "https") || proxy.Hostname() == "" {
				return nil, failure("adapter_error")
			}
			tr.Proxy = http.ProxyURL(proxy)
		}
		tr.TLSClientConfig = &tls.Config{MinVersion: tls.VersionTLS12}
		defer tr.CloseIdleConnections()
		base = tr
	}
	protected := *client
	protected.Timeout = 20 * time.Second
	protected.Transport = guardedTransport{owner: r, base: base}
	originalRedirect := client.CheckRedirect
	protected.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		if len(via) >= 5 {
			return failure("remote_error")
		}
		if err := validateURL(req.URL); err != nil {
			return err
		}
		if originalRedirect != nil {
			return originalRedirect(req, via)
		}
		return nil
	}
	response, err := protected.Do(request.WithContext(r.ctx))
	if err != nil {
		r.lastFailure = err
	}
	return response, err
}
