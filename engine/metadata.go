package engine

import (
	_ "embed"
	"encoding/json"
)

//go:embed upstream.json
var manifest []byte

func PinnedCommit() string {
	var pin struct {
		Commit string `json:"commit"`
	}
	if json.Unmarshal(manifest, &pin) != nil {
		panic("invalid embedded upstream manifest")
	}
	return pin.Commit
}
