name=$1

contracts=( 'BtcLightClient' "Burn" "CandidateHub" "GovHub" \
    "PledgeAgent" "RelayerHub" "SlashIndicator" "SystemRewad" \
    "TeamVesting" "ValidatorSet" )

for e in ${contracts[@]}
do
  echo "$e"
  ~/Downloads/solc-macos  --overwrite --abi -o ./abi contracts/${e}.sol
done
#~/Downloads/solc-macos --bin -o ./TC_$name contracts/$name.sol

#abigen --bin=./$name/$name.bin --abi=./$name/$name.abi --pkg=$name --out=./$name/$name.go

