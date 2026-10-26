import {test} from 'node:test';
import assert from 'node:assert/strict';
import {defaultLayout,normalizeLayout,layoutGroups,moveGroup} from './custom-layout.js';

test('sizes are bounded and cards retain room for names and positions',()=>{
  const layout=normalizeLayout({...defaultLayout(),columns:3,cardHeight:52,photoSize:100,fontSize:24,groups:{FC:{span:12,height:-4,hidden:true}}});
  assert.equal(layout.photoSize,40);assert.equal(layout.fontSize,13);
  assert.deepEqual(layout.groups.FC,{span:3,height:0,hidden:true});
  assert.equal(normalizeLayout({columns:NaN}).columns,12);
});
test('saved ordering survives filtering and newly added groups remain visible',()=>{
  const groups=[['New',[]],['FC',[]],['Office',[]]];
  const layout={...defaultLayout(),order:['Office','Missing','FC']};
  assert.deepEqual(layoutGroups(groups,layout).map(([n])=>n),['Office','FC','New']);
  assert.deepEqual(layoutGroups(groups.filter(([n])=>n!=='Office'),layout).map(([n])=>n),['FC','New']);
});
test('drag and keyboard moves retain every group exactly once',()=>{
  assert.deepEqual(moveGroup(['A','B','C'],'C','A'),['C','A','B']);
  assert.deepEqual(moveGroup(['A','B','C'],'B','A'),['B','A','C']);
  assert.deepEqual(normalizeLayout({order:['A','A',7]}).order,['A']);
});
