import unittest
import test_plant_workflows as legacy
import plant_workflows


def layout():
    return {'enabled':True,'columns':12,'gap':10,'cardWidth':190,'cardHeight':72,'photoSize':44,'fontSize':13,
            'sort':'position','groups':{'SENDAYAN / OFFICE':{'span':6,'height':100,'hidden':False}},'order':['SENDAYAN / OFFICE']}


class BoardLayoutTests(unittest.TestCase):
    setUp=legacy.PlantWorkflowTests.setUp
    tearDown=legacy.PlantWorkflowTests.tearDown
    request=legacy.PlantWorkflowTests.request
    login=legacy.PlantWorkflowTests.login
    setup_people=legacy.PlantWorkflowTests.setup_people
    site=legacy.PlantWorkflowTests.site

    def save(self,base='SENDAYAN',config=None,version=None):
        if version is None:version=self.request('/api/board-layout?base='+base.replace(' ','%20'))[1]['version']
        return self.request('/api/board-layout','PUT',{'base':base,'layout':layout() if config is None else config,'version':version})

    def test_shared_state_is_persisted_and_emits_revision(self):
        self.setup_people();before=self.server.store.revision
        status,result=self.save();self.assertEqual(status,200,result)
        self.assertGreater(self.server.store.revision,before)
        state=self.request('/api/state')[1]
        self.assertEqual(state['board_layouts']['SENDAYAN']['layout'],layout())
        self.assertEqual(state['board_layouts']['PORT KLANG']['layout'],{})
        with self.server.store.connect() as db:
            self.assertEqual(plant_workflows.board_layout(db,'SENDAYAN'),result)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='board_layout_updated'").fetchone()[0],1)

    def test_plant_admin_can_save_only_own_layout_and_state_is_scoped(self):
        self.setup_people();self.site()
        self.assertEqual(self.save()[0],200)
        self.assertEqual(self.request('/api/board-layout?base=PORT%20KLANG')[0],403)
        self.assertEqual(self.save('PORT KLANG',version='wrong')[0],403)
        self.assertEqual(self.save('',version='wrong')[0],403)
        self.assertEqual(set(self.request('/api/state')[1]['board_layouts']),{'SENDAYAN'})

    def test_stale_editor_cannot_overwrite_another_display(self):
        self.setup_people();old=self.request('/api/board-layout?base=SENDAYAN')[1]['version']
        self.assertEqual(self.save(version=old)[0],200)
        self.assertEqual(self.save(config={**layout(),'gap':20},version=old)[0],409)
        self.assertEqual(self.request('/api/board-layout?base=SENDAYAN')[1]['layout']['gap'],10)

    def test_invalid_geometry_is_rejected_without_losing_saved_layout(self):
        self.setup_people();self.assertEqual(self.save()[0],200)
        for change in [{'columns':0},{'cardHeight':True},{'sort':'unknown'},{'photoSize':100},{'groups':{'x':{'span':13,'height':0,'hidden':False}}},{'order':['x','x']}]:
            self.assertEqual(self.save(config={**layout(),**change})[0],400,change)
        self.assertEqual(self.request('/api/board-layout?base=SENDAYAN')[1]['layout'],layout())

    def test_employee_admin_cannot_change_layout(self):
        self.setup_people();self.site(role='employee_admin')
        self.assertEqual(self.request('/api/board-layout?base=SENDAYAN')[0],403)
        self.assertEqual(self.save(version='wrong')[0],403)


if __name__=='__main__':unittest.main()
