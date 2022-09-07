# build default archives
Files needed to build default archives (*.pak)

To build default archives from this directory:
```
../../pakbuild.py bmc_empty.manifest -o ../ -n bmc
../../pakbuild.py cust_empty.manifest -o ../ -n cust
../../pakbuild.py host_empty.manifest -o ../ -n host
../../pakbuild.py rsvd_empty.manifest -o ../ -n rsvd

# remove generated manifests
rm ../*.manifest
```
