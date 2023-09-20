name=$1

contracts=( "BtcLightClient" "Burn" "CandidateHub" "Foundation" "GovHub" \
    "PledgeAgent" "RelayerHub" "SlashIndicator" "SystemReward" \
    "ValidatorSet" )

for e in ${contracts[@]}
do
  echo "$e"
    solc --optimize --overwrite --abi -o ./abi contracts/${e}.sol
done
#~/Downloads/solc-macos --bin -o ./TC_$name contracts/$name.sol

#abigen --bin=./$name/$name.bin --abi=./$name/$name.abi --pkg=$name --out=./$name/$name.go

