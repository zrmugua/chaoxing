// Platform request boundary, maintained by the management platform.
package xuexitong

import (
    "net/http"
    "net/url"
    "strings"
)

var ConsoleRequestHook func(*http.Client, *http.Request) (*http.Response, error)

func platformDo(client *http.Client, request *http.Request) (*http.Response, error) {
    if ConsoleRequestHook != nil { return ConsoleRequestHook(client, request) }
    return client.Do(request)
}

func platformPostForm(client *http.Client, endpoint string, values url.Values) (*http.Response, error) {
    request, err := http.NewRequest("POST", endpoint, strings.NewReader(values.Encode()))
    if err != nil { return nil, err }
    request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
    return platformDo(client, request)
}
