import {test} from 'node:test';
import assert from 'node:assert/strict';
import {boardHeight,paginateBoard} from './board-layout.js';

test('large-photo TV pages fit native 1366x768 and preserve every employee',()=>{
  const groups=Array.from({length:10},(_,i)=>[i?'Group '+i:'OFFICE',Array.from({length:i?16:29},(_,j)=>({id:i+'-'+j,team:j%2?'A':'B'}))]);
  const dimensions={width:1342,height:610};
  const pages=paginateBoard(groups,dimensions);
  assert.ok(pages.length>1);
  for(const page of pages)assert.ok(boardHeight(page,dimensions)<=dimensions.height);
  const expected=groups.flatMap(([,people])=>people.map(p=>p.id));
  const actual=pages.flatMap(groups=>groups.flatMap(([,people])=>people.map(p=>p.id)));
  assert.deepEqual(actual,expected);
  assert.equal(new Set(actual).size,173);
});
test('small screens still paginate without losing people and empty boards have one empty page',()=>{
  const groups=[['OFFICE',[{id:'1'},{id:'2'},{id:'3'}]]];
  assert.equal(paginateBoard(groups,{width:350,height:100}).length,3);
  assert.deepEqual(paginateBoard([],{width:350,height:100}),[[]]);
});
