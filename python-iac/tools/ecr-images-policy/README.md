# ECR Policy Script

This script can be used to get and set the lifecycle policy of ECR repos

- To get lifecycle policy of a single repo in us-east-1, we can execute it like this
`python ecr-images-policy.py --action get-lifecycle-policy --repoName name-of-repo --region us-east-1`

- To get lifecycle policy of all repositories in us-east-1, we can execute it like this
`python ecr-images-policy.py --action get-lifecycle-policy --region us-east-1`

- To set lifecycle policy on a single repo in us-east-1 with (default) policy to retain 1 untagged image and 5 tagged images, we can execute it like this
`python ecr-images-policy.py --action set-lifecycle-policy --repoName name-of-repo --region us-east-1`

- To set lifecycle policy on a single repo in us-east-1 with a policy to retain 1 untagged image and provided tagged images count, we can execute it like this
`python ecr-images-policy.py --action set-lifecycle-policy --repoName name-of-repo --pruneAllImagesCount 10 --region us-east-1`

- To set lifecycle policy on all repositories in us-east-1 with (default) policy to retain 1 untagged image and 5 tagged images, we can execute it like this
`python ecr-images-policy.py --action set-lifecycle-policy --region us-east-1`

- To set lifecycle policy on all repositories in us-east-1 with a policy to retain 1 untagged image and 10 tagged images, we can execute it like this
`python ecr-images-policy.py --action set-lifecycle-policy --pruneAllImagesCount 10 --region us-east-1`
