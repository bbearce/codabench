import os, pdb
from datetime import datetime, timedelta
from django.utils import timezone
from django.urls import reverse

from factories import UserFactory
from ..utils import SeleniumTestCase
from django.core.exceptions import ObjectDoesNotExist

from competitions.models import Competition, CompetitionParticipant
from competitions.models import Submission
from datasets.models import Data
from profiles.models import User

# New
from django.db.models import Q
from analytics.tasks import create_storage_analytics_snapshot
from utils.storage import md5
from tasks.models import Solution
from decimal import Decimal

from PIL import Image, ImageChops, ImageStat

LONG_WAIT = 4
SHORT_WAIT = 0.2

class TestAnalyticsUI(SeleniumTestCase):
    def setUp(self):
        super().setUp()
        self.user = UserFactory(password='test')
        self.user.username = 'user1'
        self.user.email = 'user1@codabench.org'
        self.user.is_staff = True
        self.user.is_superuser = True  # Set the user as a superuser        
        self.user.save()  # Save the user with superuser status
        # Make users
        num_users = 2
        for i in range(2, num_users+1):
            user = UserFactory(password='test')
            user.username = f'user{i}'
            user.email = f'user{i}@codabench.org'
            user.is_staff = True
            user.is_superuser = True  # Set the user as a superuser
            user.save()  # Save the user with superuser status

        self.login(self.user.username, 'test')

    def current_server_time_exists(self):
        # Get server time element
        element = self.find('#server_time')
        text = element.get_attribute('innerText')

        # Check that the text is a valid datetime by loading it with strptime.
        # This will raise a ValueError if the format is incorrect.
        assert datetime.strptime(text, '%B %d, %Y, %I:%M %p %Z')

    def _upload_competition(self, competition_zip_path):
        """Creates a competition and waits for success message.

        :param competition_zip_path: Relative to test_files/ dir
        """
        self.get(reverse('competitions:upload'))
        self.find('input[ref="file_input"]').send_keys(os.path.join(self.test_files_dir, competition_zip_path))
        self.circleci_screenshot(name='uploading_comp.png')

        assert self.element_is_visible('div .ui.success.message')

        comp = self.user.competitions.first()
        comp_url = reverse("competitions:detail", kwargs={"pk": comp.id})
        self.find(f'a[href="{comp_url}"]').click()
        self.assert_current_url(comp_url)
        self.current_server_time_exists()

    def _run_submission_and_add_to_leaderboard(self, competition_zip_path, submission_zip_path, expected_submission_output, has_solutions=True, timeout=600, precision=2):
        """Creates a competition and runs a submission inside it, waiting for expected output to
        appear in submission realtime output panel.

        :param competition_zip_path: Relative to test_files/ dir
        :param submission_zip_path: Relative to test_files/ dir
        """
        self.login(username=self.user.username, password='test')

        # Upload comp steps
        # self.get(reverse('competitions:upload'))
        # self.find('input[ref="file_input"]').send_keys(os.path.join(self.test_files_dir, competition_zip_path))
        # assert self.element_is_visible('div .ui.success.message')

        # competition = self.user.competitions.first() # comp user uploaded
        competition = Competition.objects.first()
        comp_url = reverse("competitions:detail", kwargs={"pk": competition.id})
        # pdb.set_trace()
        submission_full_path = os.path.join(self.test_files_dir, submission_zip_path)
        self.get(f'{comp_url}')
        self.assert_current_url(comp_url)
        # print("1"); pdb.set_trace()
        # This clicks the page before it loads fully, delay it a bit...
        self.wait(LONG_WAIT)
        self.find('.item[data-tab="participate-tab"]').click()
        # print("2"); pdb.set_trace()
        self.circleci_screenshot("set_submission_file_name.png")
        self.find('input[ref="file_input"]').send_keys(submission_full_path)
        self.circleci_screenshot(name='uploading_submission.png')
        # print("3"); pdb.set_trace()
        # The accordion shows "Running submission.zip"
        assert self.find_text_in_class('.submission-output-container .title', f"Running {submission_zip_path}", timeout=timeout)

        # Inside the accordion the output is being streamed
        # print("4"); pdb.set_trace()
        self.wait(LONG_WAIT)
        self.find('.submission-output-container .title').click()
        self.wait(LONG_WAIT)
        assert self.find_text_in_class('.submission_output', expected_submission_output, timeout=timeout)

        # The submission table lists our submission!
        assert self.find('submission-manager#user-submission-table table tbody tr:nth-of-type(1) td:nth-of-type(2)').text == submission_zip_path
        # print("5"); pdb.set_trace()
        # Check that md5 information was stored correctly
        submission_md5 = md5(f"./src/tests/functional{submission_full_path}")
        assert Submission.objects.filter(md5=submission_md5).exists()
        if has_solutions:
            assert Solution.objects.filter(md5=submission_md5).exists()

        # Get the submission ID for later comparison
        submission_id = int(self.find('submission-manager#user-submission-table table tbody tr:nth-of-type(1) td:nth-of-type(1)').text)

        # Add the submission to the leaderboard and go to results tab
        self.find('submission-manager#user-submission-table table tbody tr:nth-of-type(1) td:nth-of-type(6) span[data-tooltip="Add to Leaderboard"]').click()
        self.find('.item[data-tab="results-tab"]').click()

        # The leaderboard table lists our submission
        prediction_score = Submission.objects.get(pk=submission_id).scores.first().score
        # pdb.set_trace()

        row_num = int(self.user.username.replace("user",""))
        self.wait(SHORT_WAIT)
        self.find('th[selenium="Leaderboard_Participant_Tab"]').click()
        assert Decimal(self.find(f'leaderboards table tbody tr:nth-of-type({row_num}) td:nth-of-type(5)').text) == round(Decimal(prediction_score), precision)

    def test_overview_storage_analytics(self):
        # Upload competition and make submission as user1
        self._upload_competition('competition.zip')
        self._run_submission_and_add_to_leaderboard('competition.zip', 'submission.zip', 'Scores')
        # Add other users to competition

        competition = Competition.objects.first()
        # competition.published = True; competition.save()
        # Make submission for each user
        num_users = 2
        users = [f'user{i}' for i in range(1,num_users+1)]
        user1 = User.objects.filter(username='user1').first()
        # pdb.set_trace()
        for user in users[1:]:
            self.user = User.objects.filter(username=user).first()
            cp = CompetitionParticipant(user_id=self.user.id, competition_id=competition.id)
            cp.status = 'approved'
            cp.save()
            # Make a submission
            self._run_submission_and_add_to_leaderboard('competition.zip', 'submission.zip', 'Scores')
            self.wait(SHORT_WAIT)
            # pdb.set_trace()
        self.wait(LONG_WAIT)        
        # pdb.set_trace()
        # Time points
        current_year = datetime.now(timezone.utc).year
        time_points = [timezone.make_aware(datetime(current_year, i, 1)) for i in range(1,len(users)+2)] # need 1 more than users
        # Make base line storage records that are blank
        create_storage_analytics_snapshot(from_selenium_test=time_points[0])
        # Edit Competition to first time point
        Competition.created_when = time_points[0]
        # Edit Datasets for competition and sync to first data point
        competition_datasets = Data.objects.filter(type__in=['competition_bundle','ingestion_program','input_data','scoring_program', 'reference_data','solution'])
        for comp_dataset in competition_datasets:
            comp_dataset.created_when = time_points[0]; comp_dataset.save
        # Edit Users and submissions
        for i, username in enumerate(users):
            # First user -> first timepoint
            # Second user -> second timepoint
            user = User.objects.filter(username=username).first()
            user.date_joined = time_points[i]; user.save()
            # Edit Submissions
            submissions = Submission.objects.filter(owner_id = user.id)
            for submission in submissions:
                submission.created_when = time_points[i]; submission.save()
            submission_datasets = Data.objects.filter(Q(type__in=['submission']) & Q(created_by_id=user.id))
            for s_dataset in submission_datasets:
                s_dataset.created_when = time_points[i]; s_dataset.save()           
            # Create second time point data in analytics tables
            create_storage_analytics_snapshot(from_selenium_test=time_points[i+1])
        # pdb.set_trace()
        # create_storage_analytics_snapshot(from_selenium_test=timezone.make_aware(datetime(current_year, 12, 30)))

        # Storage Tab
        # Resize for screenshots
        self.set_window_size(1200, 1200)
        self.get('/analytics')
        self.execute_script(f"x = document.getElementById('header'); console.log(x.style.display); x.style.display = 'None'")
        
        self.find('a[selenium="storage"]').click()
        self.find('div[selenium="This_Month_Dropdown"]').click()
        self.find('div[selenium="This_Month_Dropdown_Year"]').click()
        self.wait(LONG_WAIT)
        self.screenshot("artifacts/Usage-History-Tab.png")
        self.screenshot("src/tests/functional/test_files/Usage-History-Tab.png") # Ground Truth

        self.find('a[selenium="competitions-usage"]').click()
        pdb.set_trace()
        self.find(f'div.ui.search.multiple.selection.dropdown').click()
        for i in range(1,len(Competition.objects.all()) + 1):
            self.find(f'div.menu.transition.visible div.item:nth-child({i})').click()
        # self.find(f'div.menu.transition.visible div.item:nth-child({1})').click()
        # self.find('button[selenium="select_top_5_biggest_competitions"]').click()
        # self.find('select[ref="users_dropdown"]').click()
        self.wait(LONG_WAIT)
        self.screenshot("artifacts/Competitions-Usage-Tab.png")
        self.screenshot("src/tests/functional/test_files/Competitions-Usage-Tab.png") # Ground Truth
        
        self.find('a[selenium="users-usage"]').click()
        # self.find('button[selenium="select_top_5_biggest_users"]').click()
        pdb.set_trace()
        self.find(f'div.ui.search.multiple.selection.dropdown').click()
        for i in range(1,num_users+1):
            self.find(f'div.menu.transition.visible div.item:nth-child({i})').click()
        self.wait(LONG_WAIT)
        self.screenshot("artifacts/Users-Usage-Tab.png")
        self.screenshot("src/tests/functional/test_files/Users-Usage-Tab.png") # Ground Truth

        artifacts_usage_history_tab = Image.open('artifacts/Usage-History-Tab.png').convert('L')
        artifacts_competitions_usage_tab = Image.open('artifacts/Competitions-Usage-Tab.png').convert('L')
        artifacts_users_usage_tab = Image.open('artifacts/Users-Usage-Tab.png').convert('L')
        test_files_usage_history_tab = Image.open('src/tests/functional/test_files/Usage-History-Tab.png').convert('L')
        test_files_competitions_usage_tab = Image.open('src/tests/functional/test_files/Competitions-Usage-Tab.png').convert('L')
        test_files_users_usage_tab = Image.open('src/tests/functional/test_files/Users-Usage-Tab.png').convert('L')
        # Compare images
        difference_storage_benchmarks_tab = ImageChops.difference(artifacts_usage_history_tab, test_files_usage_history_tab)
        difference_competitions_usage_tab = ImageChops.difference(artifacts_competitions_usage_tab, test_files_competitions_usage_tab)
        difference_users_usage_tab = ImageChops.difference(artifacts_users_usage_tab, test_files_users_usage_tab )
        # Save diff
        difference_storage_benchmarks_tab.save('artifacts/difference_Usage-History-Tab.png')
        difference_competitions_usage_tab.save('artifacts/difference_Competitions-Usage-Tab.png')
        difference_users_usage_tab.save('artifacts/difference_Users-Usage-Tab.png')
        # Calculate the mean value of the difference image
        difference_storage_benchmarks_tab_stat = ImageStat.Stat(difference_storage_benchmarks_tab)
        difference_competitions_usage_tab_stat = ImageStat.Stat(difference_competitions_usage_tab)
        difference_users_usage_tab_stat = ImageStat.Stat(difference_users_usage_tab)
        # Check if all RGB channels have a mean value of 0 (indicating that all pixels are black)
        difference_storage_benchmarks_tab_stat_pixels_black = all(channel_mean == 0 for channel_mean in difference_storage_benchmarks_tab_stat.mean)
        difference_competitions_usage_tab_stat_pixels_black = all(channel_mean == 0 for channel_mean in difference_competitions_usage_tab_stat.mean)
        difference_users_usage_tab_stat_pixels_black = all(channel_mean == 0 for channel_mean in difference_users_usage_tab_stat.mean)
        # pdb.set_trace()
        if difference_storage_benchmarks_tab_stat_pixels_black and difference_competitions_usage_tab_stat_pixels_black and difference_users_usage_tab_stat_pixels_black:
            print("All pixels are black which is good.")
        else:
            raise Exception("Storage: Not all diff pixels are black. Need to check artifacts folder. Look for difference_....png images.")

        # Overview Tab
        self.get('/analytics')
        self.find('div[selenium="This_Month_Dropdown"]').click()
        self.find('div[selenium="This_Month_Dropdown_Year"]').click()
        self.execute_script(f"x = document.getElementById('header'); console.log(x.style.display); x.style.display = 'None'")
        ## Text and screenshots QA
        ### Benchmarks
        self.find('a[selenium="benchmarks-created-tab-link"]').click()
        self.wait(LONG_WAIT)
        self.screenshot("artifacts/Benchmarks-Created-Tab.png")
        self.screenshot("src/tests/functional/test_files/Benchmarks-Created-Tab.png") # Ground Truth
        ui_benchmarks_created = int(self.find('div[selenium="benchmarks-created"]').text)
        ui_benchmarks_published = int(self.find('div[selenium="benchmarks-published"]').text)
        ### Submissions
        self.find('a[selenium="submissions-created-tab-link"]').click()
        self.wait(LONG_WAIT)
        self.screenshot("artifacts/Submissions-Created-Tab.png")
        self.screenshot("src/tests/functional/test_files/Submissions-Created-Tab.png") # Ground Truth
        ui_submissions_made = self.find('div[selenium="submissions-made"]').text
        ui_submissions_made = int(0 if ui_submissions_made == '' else ui_submissions_made)
        ### Users
        self.find('a[selenium="users-created-tab-link"]').click()
        self.wait(LONG_WAIT)
        self.screenshot("artifacts/Users-Total-Tab.png")
        self.screenshot("src/tests/functional/test_files/Users-Total-Tab.png") # Ground Truth
        ui_users_total = self.find('div[selenium="users-total"]').text
        ui_users_total = int(0 if ui_users_total == '' else ui_users_total) # text says users joined)
        ### QA Text
        database_benchmarks_created = len(Competition.objects.all())
        try:
            database_benchmarks_published = Competition.objects.get(published=True)
        except ObjectDoesNotExist:
            print("Can't find published Competition")
            database_benchmarks_published = 0
        database_submissions_made = len(Submission.objects.all())
        database_users_total = len(User.objects.all())
        assert ui_benchmarks_created==database_benchmarks_created
        assert ui_benchmarks_published==database_benchmarks_published
        assert ui_submissions_made==database_submissions_made
        assert ui_users_total==database_users_total # Curently failing
        ### QA Images
        artifacts_benchmarks_created_tab = Image.open('artifacts/Benchmarks-Created-Tab.png').convert('L')
        artifacts_submissions_created_tab = Image.open('artifacts/Submissions-Created-Tab.png').convert('L')
        artifacts_users_total_tab = Image.open('artifacts/Users-Total-Tab.png').convert('L')
        test_files_benchmarks_created_tab = Image.open('src/tests/functional/test_files/Benchmarks-Created-Tab.png').convert('L')
        test_files_submissions_created_tab = Image.open('src/tests/functional/test_files/Submissions-Created-Tab.png').convert('L')
        test_files_users_total_tab = Image.open('src/tests/functional/test_files/Users-Total-Tab.png').convert('L')
        # Compare images
        difference_benchmarks_created_tab = ImageChops.difference(artifacts_benchmarks_created_tab, test_files_benchmarks_created_tab)
        difference_submissions_created_tab = ImageChops.difference(artifacts_submissions_created_tab, test_files_submissions_created_tab)
        difference_users_total_tab = ImageChops.difference(artifacts_users_total_tab, test_files_users_total_tab )
        # Save diff
        difference_benchmarks_created_tab.save(selenium="users-total"="users-total"'artifacts/difference_Benchmarks-Created-Tab.png')
        difference_submissions_created_tab.save('artifacts/difference_Submissions-Created-Tab.png')
        difference_users_total_tab.save('artifacts/difference_Users-Total-Tab.png')
        # Calculate the mean value of the difference image
        difference_benchmarks_created_tab_stat = ImageStat.Stat(difference_benchmarks_created_tab)
        difference_submissions_created_tab_stat = ImageStat.Stat(difference_submissions_created_tab)
        difference_users_total_tab_stat = ImageStat.Stat(difference_users_total_tab)
        # Check if all RGB channels have a mean value of 0 (indicating that all pixels are black)
        difference_benchmarks_created_tab_stat_pixels_black = all(channel_mean == 0 for channel_mean in difference_benchmarks_created_tab_stat.mean)
        difference_submissions_created_tab_stat_pixels_black = all(channel_mean == 0 for channel_mean in difference_submissions_created_tab_stat.mean)
        difference_users_total_tab_stat_pixels_black = all(channel_mean == 0 for channel_mean in difference_users_total_tab_stat.mean)
        # pdb.set_trace()
        if difference_benchmarks_created_tab_stat_pixels_black and difference_submissions_created_tab_stat_pixels_black and difference_users_total_tab_stat_pixels_black:
            print("All pixels are black which is good.")
        else:
            raise Exception("Overview Tab: Not all diff pixels are black. Need to check artifacts folder. Look for difference_....png images.")