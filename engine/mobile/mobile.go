// Package mobile exposes the isolated Yatori pipe runtime to Android services.
package mobile

import (
	"chaoxing-console/engine/runtime"
	"os"
)

func Serve(inputFD, outputFD int) {
	input := os.NewFile(uintptr(inputFD), "yatori-input")
	output := os.NewFile(uintptr(outputFD), "yatori-output")
	defer input.Close()
	defer output.Close()
	runtime.Serve(input, output)
}
