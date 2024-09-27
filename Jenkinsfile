properties([disableConcurrentBuilds(abortPrevious: true)])

ansiColor('xterm') {
    timestamps {
        load_library ebmc_pipelines: 'main'

        if (env?.CHANGE_ID) {
            // commit action - currently nothing defined
        } else {
            merge_action()
        }
    }
}

// Actions after a PR is merged.
def merge_action(kwargs=[:]) {
    node('lite') {
        def status = "SUCCESS"
        try {
            stage('Publish') {
                cleanWs()

                // This checks out the branch from the base repository in which
                // the PR was recently merged.
                checkout = checkout scm

                // This simply syncs GitHub (public) with the recently merged
                // changes in the base repository.
                sh  label: 'Push GHE to GitHub',
                    script: """#!/bin/bash -e
git remote add github git@github.com:open-power/op-image-tools.git
git push --follow-tags github $BRANCH_NAME
"""
            }
        } catch (e) {
            throw_error(error: e)
            status = "FAILURE"
        } finally {
            slack.send  channel_name: '#firmware-ci-bots',
                        message: """/
Publishing open-power/op-image-tools `${status}`
<${env.BUILD_URL}console|Jenkins console>
"""
            cleanWs()
        }
    }
}
