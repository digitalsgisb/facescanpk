import {useLayoutEffect} from 'react';

let openModals=0,previousOverflow='',hadModalClass=false;
// Share the lock between profile/correction dialogs and fullscreen employee details.
export function useModalSurface(open=true){
  useLayoutEffect(()=>{
    if(!open)return;
    if(openModals++===0){
      previousOverflow=document.body.style.overflow;
      hadModalClass=document.body.classList.contains('modal-open');
      document.body.style.overflow='hidden';
      document.body.classList.add('modal-open');
    }
    return()=>{
      if(--openModals===0){
        document.body.style.overflow=previousOverflow;
        if(!hadModalClass)document.body.classList.remove('modal-open');
      }
    };
  },[open]);
}
