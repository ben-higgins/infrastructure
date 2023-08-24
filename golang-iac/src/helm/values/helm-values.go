package values

import (
	"bufio"
	"log"
	"os"
	"strings"
)

func GetHelmValue(helmValuesPath, keyPair string) bool {
	var value bool = false
	// load file into param
	f, err := os.Open(helmValuesPath)
	if err != nil {
		log.Println("Error reading values.yaml file:", err)
	}

	defer f.Close()
	scanner := bufio.NewScanner(f)

	for scanner.Scan() {
		if strings.Contains(scanner.Text(), keyPair) {
			if strings.Contains(scanner.Text(), "true") {
				value = true
			}
		}
	}

	return value
}
