// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

abstract contract Updatable { 
 /* @dev this is an empty contract (no state no logic) is used to mark platform contracts that can be updated
    by the golang engine. such contracts must adhere to the following rules to avoid breaking of storage layout:     
       a. avoid declaring a constructor
       b. avoid modifying the storage layout of the platform contract: 
         b1. existing state-vars may no be removed, re-ordered or have their type changed
         b2. but existing state-vars may be renamed
         b3. new state-vars may only be appended i.e. added after the last existing state-var
         b4. constant or immutable state-vars do not take up storage slots so they may be added anywhere
       c. avoid appending any new state-vars (even not append!) to the System base contract
          explanation: the Solidity storage model, a bit like that that of C++, 
          is sequenncially constructed starting at the base contract and moving to the derived contracts.
          so for a 'contract Derived is Base1, Base2' the storage layout will be:
                - storage of Base1, followed by:
                - storage of Base2, followed by:
                - storage of Derived
          therefore any addition to a base contract (for us: System) will result in immidiate breaking of all 
          derived contracts storage layout
       d. and for the reasons stated above: avoid adding additional stateful base contracts to any platform contract

    additionally (and not storage-related) note that platform contracts must never rely on the init() function: 
    init() is an historical function that will never be invoked in future updates

}