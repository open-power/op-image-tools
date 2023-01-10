# build default archives
Files needed to build default archives (*.pak)

To build default archives from this directory:
```
../../pakbuild bmc_empty.manifest -o ../ -n bmc
../../pakbuild cust_empty.manifest -o ../ -n cust
../../pakbuild host_empty.manifest -o ../ -n host
../../pakbuild rsvd_empty.manifest -o ../ -n rsvd

# remove generated manifests
rm ../*.manifest
```
