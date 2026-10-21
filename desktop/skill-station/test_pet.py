import unittest

from pet_support import HoverController,clamp_position,evaluation_prompt,invocation_prompt,popup_position,rank_skills


class Timers:
    def __init__(self):
        self.next=0
        self.callbacks={}

    def schedule(self,delay,callback):
        self.next+=1
        self.callbacks[self.next]=callback
        return self.next

    def cancel(self,token):
        self.callbacks.pop(token,None)

    def flush(self):
        callbacks=list(self.callbacks.values())
        self.callbacks.clear()
        for callback in callbacks:
            callback()


class HoverTests(unittest.TestCase):
    def setUp(self):
        self.timers=Timers()
        self.events=[]
        self.hover=HoverController(self.timers.schedule,self.timers.cancel,
                                   lambda:self.events.append('show'),lambda:self.events.append('hide'))

    def test_brief_pass_does_not_open(self):
        self.hover.enter('pet');self.hover.leave('pet');self.timers.flush()
        self.assertEqual(self.events,[])

    def test_crossing_gap_to_menu_cancels_hide(self):
        self.hover.enter('pet');self.timers.flush()
        self.hover.leave('pet');self.hover.enter('popup');self.timers.flush()
        self.assertTrue(self.hover.visible)
        self.assertEqual(self.events,['show'])
        self.hover.leave('popup');self.timers.flush()
        self.assertFalse(self.hover.visible)
        self.assertEqual(self.events,['show','hide'])

    def test_pinned_menu_stays_until_unpinned(self):
        self.hover.show_now();self.hover.set_pinned(True)
        self.hover.leave('pet');self.timers.flush()
        self.assertTrue(self.hover.visible)
        self.hover.set_pinned(False);self.timers.flush()
        self.assertFalse(self.hover.visible)

    def test_close_cancels_delayed_reopen(self):
        self.hover.enter('pet');self.hover.dismiss();self.timers.flush()
        self.assertFalse(self.hover.visible)
        self.assertEqual(self.events,['hide'])

    def test_dropdown_grab_keeps_menu_open_past_hide_delay(self):
        self.hover.enter('popup');self.timers.flush()
        self.hover.hold_open('category-menu')
        self.hover.leave('popup');self.timers.flush()
        self.assertTrue(self.hover.visible)
        self.assertEqual(self.events,['show'])
        self.hover.release_open('category-menu');self.timers.flush()
        self.assertFalse(self.hover.visible)

    def test_dropdown_cancels_hide_that_was_already_scheduled(self):
        self.hover.show_now();self.hover.leave('popup')
        self.hover.hold_open('category-menu');self.timers.flush()
        self.assertTrue(self.hover.visible)

    def test_dropdown_selection_inside_panel_does_not_dismiss_it(self):
        self.hover.show_now();self.hover.hold_open('category-menu')
        self.hover.leave('popup');self.hover.enter('popup')
        self.hover.release_open('category-menu');self.timers.flush()
        self.assertTrue(self.hover.visible)
        self.hover.leave('popup');self.timers.flush()
        self.assertFalse(self.hover.visible)

    def test_finishing_dropdown_does_not_override_user_pin(self):
        self.hover.show_now();self.hover.set_pinned(True)
        self.hover.hold_open('category-menu');self.hover.leave('popup')
        self.hover.release_open('category-menu');self.timers.flush()
        self.assertTrue(self.hover.visible)
        self.assertTrue(self.hover.pinned)


class PocketTests(unittest.TestCase):
    def test_popup_is_on_screen_at_all_four_corners(self):
        for pet in [(0,0,144,144),(1776,0,144,144),(0,936,144,144),(1776,936,144,144)]:
            x,y=popup_position(pet,(0,0,1920,1080),(420,550))
            self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
            self.assertLessEqual(x+420,1920);self.assertLessEqual(y+550,1080)

    def test_popup_supports_negative_monitor_coordinates(self):
        x,y=popup_position((-140,850,140,140),(-1920,0,1920,1080),(420,550))
        self.assertGreaterEqual(x,-1920);self.assertLessEqual(x+420,0)
        self.assertGreaterEqual(y,0);self.assertLessEqual(y+550,1080)

    def test_saved_position_is_recovered_on_current_screen(self):
        self.assertEqual(clamp_position(9000,-300,(0,30,1920,1000),(144,144)),(1776,30))

    def test_skill_selection_excludes_disabled_and_respects_namespace(self):
        skill={'name':'Presentations','invocation':'presentations:Presentations','title':'演示文稿','summary':'制作 PPT'}
        disabled={'name':'disabled','title':'PPT','enabled':False}
        rows=rank_skills([skill,disabled],'PPT 汇报')
        self.assertEqual(rows,[skill])
        self.assertEqual(invocation_prompt(skill,'制作汇报'),'使用 $presentations:Presentations，制作汇报')

    def test_online_prompt_keeps_original_demand_and_no_install(self):
        result=evaluation_prompt({'source':'vendor/repo','slug':'demo','url':'https://skills.sh/vendor/repo/demo'},'React 性能排查')
        self.assertIn('React 性能排查',result)
        self.assertIn('先评估，不安装',result)


if __name__=='__main__':
    unittest.main()
