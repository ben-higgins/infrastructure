package helm

import (
	"context"
)

func DeployHelm() {

	opt := &KubeConfClientOptions{
		Options: &Options{
			Namespace:        "default", // Change this to the namespace you wish to install the chart in.
			RepositoryCache:  "/tmp/.helmcache",
			RepositoryConfig: "/tmp/.helmrepo",
			Debug:            true,
			Linting:          true, // Change this to false if you don't want linting.
			DebugLog: func(format string, v ...interface{}) {
				// Change this to your own logger. Default is 'log.Printf(format, v...)'.
			},
		},
		KubeContext: "",
		KubeConfig:  []byte{},
	}

	helmClient, err := NewClientFromKubeConf(opt, Burst(100), Timeout(10e9))
	if err != nil {
		panic(err)
	}
	_ = helmClient

	chartSpec := ChartSpec{
		ReleaseName: "etcd-operator",
		ChartName:   "/path/to/stable/etcd-operator",
		Namespace:   "default",
		UpgradeCRDs: true,
		Wait:        true,
	}

	if _, err := helmClient.InstallOrUpgradeChart(context.Background(), &chartSpec, nil); err != nil {
		panic(err)
	}
}
