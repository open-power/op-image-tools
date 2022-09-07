# op-image-tool
image build tools for open-power

Examples (from imagBuild dir):
See ./imageBuild.py --help

Existing repos
```
./imageBuld.py  configs/odyssey/dd1/ody_pnor_dd1_image_config --ekb <path_to_ekb_repo> --sbe <path_to_sbe_repo> --output output --name pnor.bin
```
Clone and build repos.   In this example, the location where the ekb and sbe repositories should be cloned to, and which commit to use, are specified in the config
```
./imageBuild.py configs/odyssey/dd1/ody_pnor_dd1_image_config  --output output -name pnor.bin --build
```
