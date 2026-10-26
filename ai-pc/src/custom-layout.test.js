import {test} from 'node:test';
import assert from 'node:assert/strict';
import {defaultLayout,normalizeLayout,layoutGroups,moveGroup,cardSize,orderCards,moveCardOrder} from './custom-layout.js';

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

test('individual cards keep independent pixel dimensions and legacy layouts use defaults',()=>{
  const layout=normalizeLayout({...defaultLayout(),cards:{A:{width:300,height:110},B:{width:1000,height:-20}}});
  assert.deepEqual(cardSize(layout.cards.A,layout),{width:300,height:110});
  assert.deepEqual(cardSize(layout.cards.B,layout),{width:480,height:52});
  assert.deepEqual(cardSize(undefined,layout),{width:190,height:72});
  assert.deepEqual(normalizeLayout({}).cards,{});
  assert.deepEqual(normalizeLayout({}).cardOrder,[]);
});

test('card moves reorder only the selected team and retain other saved team ordering',()=>{
  const order=moveCardOrder(['X','Y'],['A','B','C'],'C','A');
  assert.deepEqual(order,['X','Y','C','A','B']);
  assert.deepEqual(orderCards([{id:'A'},{id:'B'},{id:'C'},{id:'New'}],order).map(e=>e.id),['C','A','B','New']);
  assert.deepEqual(moveCardOrder(order,['A','B','C'],'X','A'),order);
  assert.deepEqual(moveCardOrder(order,['A','B','C'],'A','A'),order);
});
