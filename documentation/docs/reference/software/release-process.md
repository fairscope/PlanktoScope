# Release Process

The PlanktoScope's software is released independently of the PlanktoScope's hardware; this document explains how we manage releases of the PlanktoScope OS (which contains the software which runs on a PlanktoScope, and which you can download as an SD card image), to help you to:

- Understand what you should do when we publish a new release or prerelease of the PlanktoScope OS.
- Interpret the [software product specifications](./product-specs.md) and the [software changelog](./changelog.md).

## Version numbering

The PlanktoScope OS is a combination of many individual software components; some components (such as most parts of the PlanktoScope's graphical user interface, and some of its hardware drivers) are written, maintained, and distributed by the PlanktoScope project, while other components (such as the Cockpit administration dashboard and the file browser) are written, maintained, and distributed by other open-source software projects. Each component has its own release schedule and version numbering system; the specific combination of releases and versions of all these components will change over time as these components change, and we represent each total combination of all software components by a version number assigned to a particular release of the PlanktoScope OS. For example, the _v2023.9.0_ release of the PlanktoScope OS included various software programs at one specific combination of versions, while the _v2024.0.0_ release upgraded some of those programs to newer versions.

We use a [calendar-based version numbering system](https://calver.org/) for the PlanktoScope OS, where each version number has the format `v(year).(minor).(patch)` for stable releases of the software or `v(year).(minor).(patch)-(modifier)` for testing pre-releases of the software:

- `year` is a 4-digit number representing the year (in the [Gregorian calendar](https://en.wikipedia.org/wiki/Gregorian_calendar)) in which the stable release is (or will be) published. For example, version _v2024.0.0_ was published in 2024, while version _v2025.0.0_ will be published in 2025.

- `minor` is a number which starts at 0 for the first release in each year, and increments by 1 for each release which adds new features or includes notable changes to existing features. Usually `minor` will be incremented one or two times each year. For example, version _v2025.0.0_ will be the first version published in 2025, while version _v2025.1.0_ will be the second version with notable changes to be published in 2025.

- `patch` is a number which starts at 0 for each `(year).(minor)` combination, and increments by 1 for each release which consists only of small bug fixes. For example, if there were some small bugs in _v2025.0.0_ which we wanted to patch before a _v2025.1.0_ release, we could add those patches as part of a (hypothetical) _v2025.0.1_ release. If the bugs are not very severe, we might not publish a patch release and we could instead just include those bug fixes together with other new features, in which case we would increment `minor` with the next release. For example, we might not publish a _v2025.0.1_ release, and instead just publish a _v2025.1.0_ release.

- `modifier` is an additional string included to identify "alpha" or "beta" pre-releases published for testing before the stable release. We typically publish multiple "alpha" and "beta" pre-releases with additional improvements before a stable release, so `modifier` has the format of either `alpha.(index)` or `beta.(index)`, where `index` is a number which starts at 0 for each `(year).(minor).(patch)-alpha` or `(year).(minor).(patch)-beta` combination. For example, the first "alpha" pre-release for _v2024.0.0_ was _v2024.0.0-alpha.0_, the second "alpha" pre-release was _v2024.0.0-alpha.1_, and the first "beta" pre-release was _v2024.0.0-beta.0_.

## Release channels

The PlanktoScope project uses a concept called "release channels" to structure our process for stabilizing and testing our software before we publish a new release of the PlanktoScope OS for everyone to use. There are three channels for PlanktoScope software releases and pre-releases, each corresponding to a particular branch of the [PlanktoScope repository on GitHub](https://github.com/fairscope/PlanktoScope):

- Edge: On the "Edge" channel, the PlanktoScope OS is automatically built from the latest commit of the `main` branch of the PlanktoScope repository on GitHub - so the "Edge" channel is essentially the current unstable development version of the PlanktoScope OS, and is often likely to be broken or buggy in various ways. Occasionally, specific commits on the `main` branch are tagged as "alpha" pre-releases; "alpha" pre-releases should be treated as snapshots of PlanktoScope software development for testing by PlanktoScope software developers and advanced users.
- Beta: Once an "alpha" pre-release has received sufficient testing for the PlanktoScope software developers to consider it stable enough for all PlanktoScope users to test it out, it will be promoted to a "beta" pre-release, and the `software/beta` branch of the PlanktoScope repository on GitHub will be advanced to the Git commit of the "beta" pre-release. At that point, the `software/beta` branch will only receive patches to fix serious problems. As bugs are fixed on the `software/beta` branch, more "beta" pre-releases may be created on that branch for users to test.
- Stable: After the latest "beta" pre-release has received sufficient testing for the PlanktoScope software developers to consider it stable enough for most (or, ideally, all) PlanktoScope users to rely on it for production use and scientific operations, that "beta" pre-release will be promoted to a "stable" release, and the `software/stable` branch of the PlanktoScope repository on GitHub will be advanced to the git commit of the "stable" release.

### Release schedules

We try to publish a few stable releases every year (though so far we have only published one stable release each year). We allow for the possibility that some stable releases may consist of small bugfixes, while other stable releases may add new functionalities or change existing functionalities. Thus, each release involves changes with different sizes of potential impact on software stability and different levels of risks for introducing new bugs. Because of this, we usually cannot make confident predictions about how long we will need to wait before we can promote an "alpha" pre-release to a "beta" pre-release. And because we rely on volunteers to test our "beta" pre-releases and the availability of volunteers for testing each "beta" pre-release often varies a lot, we cannot make confident predictions about how long we will need to wait before we can promote a "beta" pre-release to a "stable" release.

Although the unpredictability of "alpha" and "beta" pre-release testing timelines prevents us from being able to set realistic expectations about specific software release timelines, you can generally expect at least one stable release in each year; we aim to publish at least one stable release in the first half of each year, and at least one stable release in the second half of each year.

### Choosing a release channel

Unless you have a specific reason, you probably should follow the stable release channel. "Stable" releases are intended for a general audience to rely on.

However, we encourage all PlanktoScope users who use the stable release channel to also test beta pre-releases once those pre-releases are published. This will help us to discover and understand bugs which we may need to fix before we promote the PlanktoScope software from the "Beta" channel to the "Stable" channel.

## Upgrading to a new release or pre-release

In order to use a new release or pre-release of the PlanktoScope OS, please follow the [software reset & upgrades guide](../../operation/software-upgrades.md).
