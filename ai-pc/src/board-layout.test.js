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

test('parallel teams share height while Office retains its full-width rows',()=>{
  const workers=team=>Array.from({length:6},(_,i)=>({id:team+i,team,department:'PRODUCTION'}));
  // At 1000px each of the two teams has room for two native cards per row:
  // 3 card rows + heading + padding, rather than six sequential team rows.
  assert.equal(boardHeight([['FC',[...workers('A'),...workers('B')]]],{width:1000}),273);
  const office=workers('N').map(e=>({...e,department:'OFFICE'}));
  assert.equal(boardHeight([['PORT KLANG / OFFICE',office]],{width:1000}),170);
});

test('uneven teams, C/D and unassigned staff all survive TV and phone pagination',()=>{
  const groups=[['SENDAYAN / FC',['C','D','N',''].flatMap((team,t)=>Array.from({length:[27,13,2,1][t]},(_,i)=>({id:team+'-'+i,team,department:'PRODUCTION'})))]];
  const expected=groups[0][1].map(e=>e.id);
  for(const width of [390,1342,1896]){
    const dimensions={width,height:610};
    const pages=paginateBoard(groups,dimensions);
    assert.deepEqual(pages.flatMap(page=>page.flatMap(([,people])=>people.map(e=>e.id))),expected);
    for(const page of pages)assert.ok(boardHeight(page,dimensions)<=dimensions.height);
  }
});
