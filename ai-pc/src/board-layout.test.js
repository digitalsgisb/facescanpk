import {test} from 'node:test';
import assert from 'node:assert/strict';
import {boardHeight,paginateBoard,boardTeams,teamColumnWeight,orderBoardGroups} from './board-layout.js';

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
  // Fixed primary-team columns align across groups, including when Normal is empty.
  assert.equal(boardHeight([['FC',[...workers('A'),...workers('B')]]],{width:1000}),518);
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

test('primary shift columns keep their order and weight across uneven groups',()=>{
  const workers=(a,b,n)=>[['A',a],['B',b],['N',n]].flatMap(([team,count])=>Array.from({length:count},(_,i)=>({id:team+i,team})));
  const first=boardTeams(workers(22,11,2)),second=boardTeams(workers(5,5,0));
  assert.deepEqual(first.map(([team])=>[team,teamColumnWeight(team)]),second.map(([team])=>[team,teamColumnWeight(team)]));
  assert.equal(second.find(([team])=>team==='N')[1].length,0);
  assert.deepEqual(boardTeams([{id:'n',team:'N'}]).map(([team])=>team),['N']);
  assert.deepEqual(boardTeams([{id:'c',team:'C'}]).map(([team])=>team),['C','D','N']);
});

test('Office precedes A/B/N groups, then A/B, then Normal-only groups',()=>{
  const group=(name,teams)=>[name,teams.map((team,i)=>({id:name+i,team,department:name==='OFFICE'?'OFFICE':'PRODUCTION'}))];
  const groups=[group('OFFICE',['N']),group('FC',['A','B','N']),group('LM & SA',['N']),
    group('MF',['A','B','N']),group('ROLL MAKING',['A','B']),group('MAINTENANCE',['A','B']),
    group('QUALITY',['A','B']),group('R&D',['N']),group('STORE',['N']),group('PLANNING',['A','B','N'])];
  const ordered=orderBoardGroups(groups);
  assert.deepEqual(ordered.map(([name])=>name),['OFFICE','FC','MF','PLANNING','ROLL MAKING','MAINTENANCE','QUALITY','LM & SA','R&D','STORE']);
  assert.equal(new Set(ordered.flatMap(([,people])=>people.map(e=>e.id))).size,groups.flatMap(([,people])=>people).length);
  assert.deepEqual(groups.map(([name])=>name),['OFFICE','FC','LM & SA','MF','ROLL MAKING','MAINTENANCE','QUALITY','R&D','STORE','PLANNING']);
  const filtered=[['LM & SA',groups[2][1]],['FC',groups[1][1].filter(e=>e.team==='A')]];
  assert.deepEqual(orderBoardGroups(filtered,groups).map(([name])=>name),['FC','LM & SA']);
});

test('plant sections stay together and C/D/N uses the same shift ordering',()=>{
  const group=(plant,name,teams)=>[plant+' / '+name,teams.map(team=>({team,department:name==='OFFICE'?'OFFICE':'PRODUCTION'}))];
  const groups=[group('SENDAYAN','Normal',['N']),group('PORT KLANG','Normal',['N']),
    group('SENDAYAN','C/D',['C','D']),group('SENDAYAN','Mixed',['C','D','N']),
    group('PORT KLANG','Mixed',['A','B','N']),group('SENDAYAN','OFFICE',['N'])];
  assert.deepEqual(orderBoardGroups(groups).map(([name])=>name),[
    'PORT KLANG / Mixed','PORT KLANG / Normal','SENDAYAN / OFFICE','SENDAYAN / Mixed','SENDAYAN / C/D','SENDAYAN / Normal']);
});
