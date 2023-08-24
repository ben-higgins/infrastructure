#!/bin/bash
set -x
go run main.go \
    -action ${ACTION} \
    -bucket ${BUCKET} \
    -env ${ENV} 
