## [1.0.0-beta.18](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.17...v1.0.0-beta.18) (2026-11-07)

### Features

* **viz:** instance arrows in the browser from server anchors ([51c0d6d](https://github.com/equa/equa-cfd-viewer/commit/51c0d6d624e1c67bd4fb53428b9514e6f30f1c92))

## [1.0.0-beta.17](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.16...v1.0.0-beta.17) (2026-11-06)

### Bug Fixes

* **web:** leave the axes gizmo out of screenshots ([7835761](https://github.com/equa/equa-cfd-viewer/commit/7835761f2537819842a848180db52351335decc5))

## [1.0.0-beta.16](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.15...v1.0.0-beta.16) (2026-11-06)

### Features

* **web:** corner axes gizmo replaces the in-scene triad ([8d4a8ca](https://github.com/equa/equa-cfd-viewer/commit/8d4a8ca27a01f1c960b2b84e155ff5b2bcb4a6fb))

## [1.0.0-beta.15](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.14...v1.0.0-beta.15) (2026-11-06)

### Features

* **viz:** outline OBJ groups in geometry feature edges ([1806633](https://github.com/equa/equa-cfd-viewer/commit/180663354439aee9e07faa7eb6763455c6ce2026))

## [1.0.0-beta.14](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.13...v1.0.0-beta.14) (2026-11-06)

### Bug Fixes

* **web:** keep a leading or trailing dot while typing a number ([c97d1b4](https://github.com/equa/equa-cfd-viewer/commit/c97d1b40ab2f55880a282d76512310a48fa6c789))

## [1.0.0-beta.13](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.12...v1.0.0-beta.13) (2026-11-06)

### Features

* **web:** shared look block at the top of each part panel ([a92804d](https://github.com/equa/equa-cfd-viewer/commit/a92804d7e35ba41a2a6a086a89c79ac0fc6b4d0d))

## [1.0.0-beta.12](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.11...v1.0.0-beta.12) (2026-11-06)

### Features

* **web:** opacity by value per part ([534f9a1](https://github.com/equa/equa-cfd-viewer/commit/534f9a142bbcf8a955d0c8cd71fcaf40f5bdb653))

## [1.0.0-beta.11](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.10...v1.0.0-beta.11) (2026-11-06)

### Bug Fixes

* **web:** limit the streamline animation speed to useful values ([879a6d7](https://github.com/equa/equa-cfd-viewer/commit/879a6d75f17ac1ed09a40ecfd3f474e61bccc56c))

## [1.0.0-beta.10](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.9...v1.0.0-beta.10) (2026-11-06)

### Features

* **viewer:** freeze streamline seeds until re-seed ([4306eeb](https://github.com/equa/equa-cfd-viewer/commit/4306eeb3d6f89219c4a386fb3d7cbce30a27b45e))

## [1.0.0-beta.9](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.8...v1.0.0-beta.9) (2026-11-06)

### Bug Fixes

* **viewer:** draw the real cell edges on the boundary and crinkle slice ([d7091a8](https://github.com/equa/equa-cfd-viewer/commit/d7091a8be36374f4ddccd566a4cc3bddd187200b))

## [1.0.0-beta.8](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.7...v1.0.0-beta.8) (2026-11-06)

### Features

* **web:** make robust range live, outside Apply ([3c74710](https://github.com/equa/equa-cfd-viewer/commit/3c747106d875f94b979b3c841a29eb74e40d3293))
* **web:** set the geometry line width ([d54d336](https://github.com/equa/equa-cfd-viewer/commit/d54d33690633889e354ccd66fb60f8b6fef1325f))

## [1.0.0-beta.7](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.6...v1.0.0-beta.7) (2026-11-02)

### Bug Fixes

* **deps:** update non-major dependencies ([46aaabe](https://github.com/equa/equa-cfd-viewer/commit/46aaabe6340b06aef8b1d3cdd38d7c96bfd39ed3))

## [1.0.0-beta.6](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.5...v1.0.0-beta.6) (2026-10-30)

### Features

* **cases:** open IDA ICE project case zips through a case cache ([3a8bb84](https://github.com/equa/equa-cfd-viewer/commit/3a8bb84c014ab0dab9684d83eb1ca97c98f338ce))

### Bug Fixes

* **client:** show Opening case while a switched case loads ([9e9f075](https://github.com/equa/equa-cfd-viewer/commit/9e9f07597e5e3643bc48a44cad7a5c5e350ed685))

## [1.0.0-beta.5](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.4...v1.0.0-beta.5) (2026-10-27)

### Features

* add a local run mode for a user's own machine ([3223dd5](https://github.com/equa/equa-cfd-viewer/commit/3223dd5f880ffbdfd36deb2274d330e50653dc2e))
* **windows:** build and smoke-test a Windows bundle ([9e64da3](https://github.com/equa/equa-cfd-viewer/commit/9e64da329276d3c221f8c75ae5d8a7ba9e652c97))

### Bug Fixes

* **pipeline:** drop the deprecated VTK threshold call and its pop-up ([fd22f11](https://github.com/equa/equa-cfd-viewer/commit/fd22f115dc8bfcafee9bfce226ba942d21e4a45f))
* **windows:** compare the bundle version as PEP 440 in the smoke test ([4ecb308](https://github.com/equa/equa-cfd-viewer/commit/4ecb30828836e2acd53dcb484bb9b94f3db221fc))

## [1.0.0-beta.4](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.3...v1.0.0-beta.4) (2026-10-26)

### Bug Fixes

* **deps:** update non-major dependencies ([53b9561](https://github.com/equa/equa-cfd-viewer/commit/53b9561ebbdaa63bf863ab1231df954b68394568))
* **docker:** hold the Python image at 3.14, vtk has no 3.15 wheels ([7fd4b6b](https://github.com/equa/equa-cfd-viewer/commit/7fd4b6b7112af12916948320d253f466fabbb5b8))

## [1.0.0-beta.3](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.2...v1.0.0-beta.3) (2026-10-24)

## [1.0.0-beta.2](https://github.com/equa/equa-cfd-viewer/compare/v1.0.0-beta.1...v1.0.0-beta.2) (2026-10-24)

## 1.0.0-beta.1 (2026-10-24)

### Features

* log startup, requests, and the deep-link/load path ([5859fda](https://github.com/equa/equa-cfd-viewer/commit/5859fda8b0a2ae8d083664e618e73629f6f70178))
* preselect a case from ?case=<name> for backend embedding ([3d49c69](https://github.com/equa/equa-cfd-viewer/commit/3d49c69360eeb6c06d2d203703d25e91b957901b))
* read decomposed cases with vtkPOpenFOAMReader ([690eeb7](https://github.com/equa/equa-cfd-viewer/commit/690eeb7d183afb37eb3f89651037bb38dcf4ad9f))
* refresh time steps (button + on reopen) ([4e47034](https://github.com/equa/equa-cfd-viewer/commit/4e47034235797c7b0025ccd438bca8fa1bf6aa3c))
* run headless against an empty/dynamic case root (service mode) ([7244893](https://github.com/equa/equa-cfd-viewer/commit/7244893a863ba7a1d00c12ad183817f41c01da98))
* **server:** add /health, /api/config and --mode ([5885b61](https://github.com/equa/equa-cfd-viewer/commit/5885b610b9a601ebc49fff9b7357eea45c3bcbca))
* **server:** case sources with stable ids, labels and cheap cell counts ([453ec16](https://github.com/equa/equa-cfd-viewer/commit/453ec16ce9e06e59e258d245354549a2d39c4ed9))
* **server:** serve under ROOT_PATH and take settings from the environment ([9019b7f](https://github.com/equa/equa-cfd-viewer/commit/9019b7f4a4e540a1d7e9c00a45c83a5d8664336f))
* **web:** a start screen, and cases opened by id ([bb6d41c](https://github.com/equa/equa-cfd-viewer/commit/bb6d41c21f2ef1a4f4e98f631de64a37930a89f7))

### Bug Fixes

* **case:** read cases in place, without writing a .foam marker into them ([4d8eeeb](https://github.com/equa/equa-cfd-viewer/commit/4d8eeeba51207913f9108e8ce612005f87e7b3ac))
* empty-case startup crash that restart-loops the container ([6a3e688](https://github.com/equa/equa-cfd-viewer/commit/6a3e6880c56e7877e3d0b0e4bb62eeeec2381455))
* keep the equa-dev feed out of the image build ([84fdf16](https://github.com/equa/equa-cfd-viewer/commit/84fdf16bd5cd6fe2aae316e3a8b68971002569e8))
* middleware second parameter must be named `handler` ([99d226a](https://github.com/equa/equa-cfd-viewer/commit/99d226aa42b6d0c7c784647f263a2400d558fdba))
* **pipeline:** restore rendering_started for cfd-backend's smoke test ([14603bd](https://github.com/equa/equa-cfd-viewer/commit/14603bd4b93800afa63d3f8c5f39d587005c28ab))
* rebuild the field selectors from the loaded time step ([070fbc1](https://github.com/equa/equa-cfd-viewer/commit/070fbc199ce863c6fef6a826df5e89fa9da05295))
* **server:** find cases where cfd-backend finds them, bounded at 4 levels ([052dac1](https://github.com/equa/equa-cfd-viewer/commit/052dac1d3d58a25c040311bc85e0ec510b037511))
* **server:** report unreadable directories instead of hiding or failing on them ([473ae36](https://github.com/equa/equa-cfd-viewer/commit/473ae362d8c4add6317bc13484a5c680035132ec))
* streamline lines/tubes via two actors (not mapper-input swap); bands clamp ([86967fc](https://github.com/equa/equa-cfd-viewer/commit/86967fc5201aea0c4d2d6269565d9a4a8e0c3ba8))

### Performance Improvements

* build the render window lazily, so extraction needs no GL backend ([f63662f](https://github.com/equa/equa-cfd-viewer/commit/f63662fcde2120183fd05d6060d6029b5aeadce2))
* don't re-bake FoamVizColor on every scene update (cheap toggles) ([dd8339f](https://github.com/equa/equa-cfd-viewer/commit/dd8339fa4fc4408d9fbf1f27e1aba73009500f13))
* don't re-set active vectors every scene update (the real toggle cost) ([7dd1f3a](https://github.com/equa/equa-cfd-viewer/commit/7dd1f3a6507c8519c82a02099a0f0e31a4030d70))
* free the previous case on a switch, and trim the heap ([4a58f11](https://github.com/equa/equa-cfd-viewer/commit/4a58f11471aa098337d57fee02e6178beae75968))
* make reopening the viewer cheap (don't re-read the mesh unless a step appeared) ([72b5754](https://github.com/equa/equa-cfd-viewer/commit/72b575456c0a48a84232604c78c2dcea098265ae))
