//go:build android

// Android loads the original OCR models from the application's shared assets.
package utils

import (
	"fmt"
	"os"
	"path/filepath"

	ort "github.com/yalue/onnxruntime_go"
)

func modelPath(name string) string {
	directory := os.Getenv("YATORI_MODEL_DIR")
	if directory == "" || !filepath.IsAbs(directory) {
		panic("Android OCR model directory is unavailable")
	}
	return filepath.Join(directory, name)
}

func DDDDOcrCoreInit() {
	for _, name := range []string{"common_old.onnx", "common_tencent.onnx", "calc_det.onnx"} {
		info, err := os.Stat(modelPath(name))
		if err != nil || !info.Mode().IsRegular() || info.Size() == 0 {
			panic(fmt.Sprintf("Android OCR model is unavailable: %s", name))
		}
	}
	library := os.Getenv("YATORI_ONNX_LIBRARY")
	if library == "" || !filepath.IsAbs(library) {
		panic("Android ONNX library is unavailable")
	}
	ort.SetSharedLibraryPath(library)
	if err := ort.InitializeEnvironment(); err != nil {
		panic(err)
	}
}
