package params

import (
	"bufio"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"strings"
)

func BuildParams(paramDir string) map[string]map[string]string {
	var f []string
	var params = map[string]map[string]string{}

	entries, err := ioutil.ReadDir(paramDir)
	if err != nil {
		log.Fatal(err)
	}

	for _, d := range entries {
		if d.IsDir() {
			f = append(f, d.Name())
		}
	}

	for _, r := range f {
		params[r] = map[string]string{}
		files, err := ioutil.ReadDir(paramDir + "/" + r)
		if err != nil {
			log.Fatal(err)
		}
		for _, file := range files {
			readFile, err := os.Open(paramDir + "/" + r + "/" + file.Name())
			if err != nil {
				log.Fatal(err)
			}
			fileScanner := bufio.NewScanner(readFile)
			fileScanner.Split(bufio.ScanLines)

			for fileScanner.Scan() {
				if len(fileScanner.Text()) != 0 && fileScanner.Text()[0:1] != "#" {
					split := strings.SplitN(fileScanner.Text(), ":", 2)
					params[r][strings.TrimSpace(split[0])] = strings.TrimSpace(split[1])
				}
			}

			readFile.Close()
		}
	}

	return params
}

type keyPairs struct {
	ParameterKey   string
	ParameterValue string
}
type keyPairList struct {
	Items []keyPairs
}

func (params *keyPairList) AddItem(item keyPairs) {
	params.Items = append(params.Items, item)
}

func BuildJsonParams(paramList map[string]string) {
	params := keyPairList{}
	for key := range paramList {
		newValue := keyPairs{
			ParameterKey:   key,
			ParameterValue: paramList[key],
		}
		params.AddItem(newValue)
	}

	//bytes, _ := json.Marshal(params.Items)
	fmt.Print(params)
}
