# Contributing

First of all, thank you for contributing to the PlanktoScope! The goal of this document is to provide everything you need to know in order to contribute to PlanktoScope.

There are several ways to join the development effort, share your progress with your build or just ask for help.

We are using slack as a communication platform between interested parties. You can [request to join by filling this form](https://docs.google.com/forms/d/e/1FAIpQLSfcod-avpzWVmWj42_hW1v2mMSHm0DAGXHxVECFig2dnKHxGQ/viewform).

This repository is also a good way to get involved. Please fill in an issue if you witnessed a bug in the software or hardware. If you are able, you can also join the development effort. Look through the [issues opened](https://github.com/PlanktonPlanet/PlanktoScope/labels/good%20first%20issue) and choose one that piques your interest. Let us know you want to work on it in the comments, we may even be able to guide your beginnings around the code.

## Assumptions

1. **You're familiar with [git](https://git-scm.com/) and the [Merge Request](https://docs.gitlab.com/ee/user/project/merge_requests/creating_merge_requests.html)(PR) workflow.**
2. **You've read the PlanktoScope [documentation](../../index.md).**
3. **You know about the PlanktoScope [community on Slack](https://planktoscope.slack.com/). Please use this for help.**

## How to Contribute

1. Make sure that the contribution you want to make is explained or detailed in a GitHub issue! Find an [existing issue](https://github.com/fairscope/PlanktoScope/issues) or [open a new one](https://github.com/fairscope/PlanktoScope/issues/new/choose).
2. Once done, [fork the PlanktoScope repository](https://docs.github.com/en/get-started/quickstart/fork-a-repo) in your Github account. Ask a maintainer if you want your issue to be checked before making a PR.
3. [Create a new Git branch](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-and-deleting-branches-within-your-repository).
4. Review the [Development Workflow](#development-workflow) section that describes the steps to maintainer the repository.
5. Make the changes on your branch.
6. [Submit the branch as a PR](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request) pointing to the `main` branch of the main PlanktoScope repository. A maintainer should comment and/or review your Pull Request within a few days. Although depending on the circumstances, it may take longer. We do not enforce a naming convention for the PRs, but **please use something descriptive of your changes**, having in mind that the title of your PR will be automatically added to the next [release changelog](https://github.com/fairscope/PlanktoScope/releases).

## Git Guidelines

### Git Branches

All changes must be made in a branch and submitted as PR.
We do not enforce any branch naming style, but please use something descriptive of your changes.

### Git Commits

As minimal requirements, your commit message should:

- be capitalized
- not finish by a dot or any other punctuation character (!,?)
- start with a verb so that we can read your commit message this way: "This commit will ...", where "..." is the commit message.
  e.g.: "Fix the home page button" or "Add more tests for create_index method"

We don't follow any other convention, but if you want to use one, we recommend [this one](https://chris.beams.io/posts/git-commit/).

### Pull Requests

Some notes on PRs:

- [Convert your PR as a draft]() if your changes are a work in progress: no one will review it until you pass your PR as ready for review.<br>
  The draft PR can be very useful if you want to show that you are working on something and make your work visible.
- The branch related to the PR must be **up-to-date with `main`** before merging. Fortunately, this project [integrates a bot]() to automatically enforce this requirement without the PR author having to do it manually.
- All PRs must be reviewed and approved by at least one maintainer.
- The PR title should be accurate and descriptive of the changes. The title of the PR will be indeed automatically added to the next [release changelogs]().

## Release Process (for internal team only)

PlanktoScope tools follow the [Semantic Versioning Convention](https://semver.org/).

### Automation to Rebase and Merge the PRs

This project integrates a bot that helps us manage pull requests merging.<br>
_[Read more about this]()._

### How to Publish the Release

⚠️ Before doing anything, make sure you got through the guide about [Releasing an Integration]().

⚠️ Every PR that is merged to `main` introducing changes to the PlanktoScope needs to modify the file [``](), by increasing the version of the chart accordingly.

Every PR that is merged to `main` triggers the automated release process, as specified at [``](). A GitHub Action will be triggered and publish a new release on the GitHub repository [releases](). This will enable users to start using the new version of the chart immediately after publishing.

Thank you again for reading this through, we can not wait to begin to work with you if you made your way through this contributing guide ❤️
