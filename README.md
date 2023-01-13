# op-image-tool
image build tools for open-power

Examples (from imagBuild dir):
See ./imageBuild.py --help

The case where both ekb and sbe repos exist and they are already built
```
./imageBuld.py  configs/odyssey/dd1/ody_pnor_dd1_image_config --ekb <path_to_ekb_repo> --sbe <path_to_sbe_repo> --output output --name pnor.bin
```
The case where sbe is already built and at least the desired ekb archive(s) are in the overrides directory.
```
./imageBuild.py configs/odyssey/dd1/ody_pnor_dd1_image_config --sbe <path_to_sbe_repo> --ovrd <path_to_overrides> --output output --name pnor.bin
```
The case where the ekb and sbe need to be built. If the provided location do not exist, they will be cloned from gerrit before being built.   In this example, the location where
the ekb and sbe repositories should be cloned to, and which commit to use, are specified in the config file
```
./imageBuild.py configs/odyssey/dd1/ody_pnor_dd1_image_config  --output output --name pnor.bin --build
```
