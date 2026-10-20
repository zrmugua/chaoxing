module chaoxing-console/engine

go 1.26.0

require github.com/yatori-dev/yatori-go-core v0.0.0

require (
	github.com/PuerkitoBio/goquery v1.10.0 // indirect
	github.com/andybalholm/brotli v1.0.6 // indirect
	github.com/andybalholm/cascadia v1.3.2 // indirect
	github.com/google/uuid v1.6.0 // indirect
	github.com/klauspost/compress v1.17.4 // indirect
	github.com/nfnt/resize v0.0.0-20180221191011-83c6a9932646 // indirect
	github.com/refraction-networking/utls v1.8.2 // indirect
	github.com/thedevsaddam/gojsonq v1.9.1 // indirect
	github.com/tjfoc/gmsm v1.4.1 // indirect
	golang.org/x/crypto v0.58.0 // indirect
	golang.org/x/mobile v0.0.0-20261011034528-197770444867 // indirect
	golang.org/x/mod v0.42.0 // indirect
	golang.org/x/net v0.61.0 // indirect
	golang.org/x/sync v0.24.0 // indirect
	golang.org/x/sys v0.49.0 // indirect
	golang.org/x/text v0.43.0 // indirect
	golang.org/x/tools v0.52.0 // indirect
)

replace github.com/yatori-dev/yatori-go-core => ../third_party/yatori-go-core

tool (
	golang.org/x/mobile/cmd/gobind
	golang.org/x/mobile/cmd/gomobile
)
