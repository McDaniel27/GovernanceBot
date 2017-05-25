# Stuart McDaniel, 2017

import os
import pickle
import re
import time

import praw
import praw.models
import praw.exceptions
import prawcore.exceptions


SILVER_POINTS_THRESHOLD = 5
GOLD_POINTS_THRESHOLD = 10
NEW_POSTS_TO_READ = 10
POLL_TIME_HOURS = 0.25
POLL_TIME_SECONDS = POLL_TIME_HOURS * 60 * 60
DELETE_REPLIES_THRESHOLD = 3
VALID_SUBREDDIT_NAME_REGEX = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_]{1,20}\Z")
TOP_POSTS_TO_FORK = 10


def poll(submission):
	vote_user_names = []
	yes_reply_count = 0
	no_reply_count = 0
	for reply in submission.comments:
		if isinstance(reply, praw.models.MoreComments):
			continue
		reply_text_lower = reply.body.lower()
		user_name = reply.author.name
		if reply_text_lower[:3] == "yes":
			if user_name not in vote_user_names:
				yes_reply_count += 1
				vote_user_names.append(user_name)
		elif reply_text_lower[:2] == "no":
			if user_name not in vote_user_names:
				no_reply_count += 1
				vote_user_names.append(user_name)
	if yes_reply_count > no_reply_count:
		return True
	else:
		return False


reddit = praw.Reddit("GovernanceBot")
subreddit = reddit.subreddit("GovernanceBot")

current_unix_timestamp = int(time.time())
current_formatted_timestamp = time.strftime("%d/%m/%Y %H:%M %Z")
subreddit_name = subreddit.display_name
moderator_user_names = [moderator.name for moderator in subreddit.moderator]
banned_user_names = [banned_user.name for banned_user in subreddit.banned]
special_user_names = moderator_user_names + banned_user_names
subreddit.flair.delete_all()
subreddit.flair.set(redditor="GovernanceBot", text="GovernanceBot")

if not os.path.exists("data"):
	os.makedirs("data")
	guide = subreddit.submit(title="GovernanceBot Guide", selftext="GovernanceBot is a bot that extends the Reddit governance model to include features from other websites.\n\nThe Reddit governance model is very simple...")
	guide.mod.distinguish(how="yes")
	guide.mod.sticky(state=True)
	guide_id = guide.id
	log = subreddit.submit(title="r/" + subreddit_name + " GovernanceBot Log", selftext="r/" + subreddit_name + " GovernanceBot Log:")
	log.mod.distinguish(how="yes")
	log.mod.sticky(state=True, bottom=True)
	log_id = log.id
	posts = []
	open_ban_polls = []
	open_mod_polls = []
	open_title_polls = []
	open_delete_comments = []
else:
	with open("data/guide_log.pkl", "rb") as guide_log_file:
		guide_id, log_id = pickle.load(guide_log_file)
		log = reddit.submission(id=log_id)
	with open("data/posts.pkl", "rb") as posts_file:
		posts = pickle.load(posts_file)
	with open("data/open_ban_polls.pkl", "rb") as open_ban_polls_file:
		open_ban_polls = pickle.load(open_ban_polls_file)
	with open("data/open_mod_polls.pkl", "rb") as open_mod_polls_file:
		open_mod_polls = pickle.load(open_mod_polls_file)
	with open("data/open_title_polls.pkl", "rb") as open_title_polls_file:
		open_title_polls = pickle.load(open_title_polls_file)
	with open("data/open_delete_comments.pkl", "rb") as open_delete_comments_file:
		open_delete_comments = pickle.load(open_delete_comments_file)

user_names_points = dict()
for submission in subreddit.new(limit=1000):
	user_name = submission.author.name
	if user_name not in special_user_names + [None]:
		if user_name not in user_names_points.keys():
			user_names_points[user_name] = submission.score
		else:
			user_names_points[user_name] += submission.score
for comment in subreddit.comments(limit=1000):
	user_name = comment.author.name
	if user_name not in special_user_names + [None]:
		if user_name not in user_names_points.keys():
			user_names_points[user_name] = comment.score
		else:
			user_names_points[user_name] += comment.score
user_names_flairs = []
for user_name in user_names_points.keys():
	user_points = user_names_points[user_name]
	if user_points >= GOLD_POINTS_THRESHOLD:
		user_names_flairs.append({"user": user_name, "flair_text": "GOLD (" + str(user_points) + ")"})
	elif user_points >= SILVER_POINTS_THRESHOLD:
		user_names_flairs.append({"user": user_name, "flair_text": "SILVER (" + str(user_points) + ")"})
	else:
		user_names_flairs.append({"user": user_name, "flair_text": "BRONZE (" + str(user_points) + ")"})
subreddit.flair.update(flair_list=user_names_flairs)
log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Updated all subreddit points.")

if subreddit.new(limit=NEW_POSTS_TO_READ) is not None:
	for submission in subreddit.new(limit=NEW_POSTS_TO_READ):
		submission_id = submission.id
		if submission_id not in posts + [guide_id, log_id]:
			posts.append(submission_id)
			submission_is_self = submission.is_self
			submission_title = submission.title
			submission_title_lower = submission_title.lower()
			if submission_is_self and submission_title_lower[:17] == "delete privilege:":
				try:
					delete_submission = reddit.submission(id=submission_title_lower[18:])
					if delete_submission.subreddit == subreddit:
						if delete_submission.selftext != "[deleted]":
							delete_submission_id = delete_submission.id
							delete_submission_title = delete_submission.title
							sub_user = submission.author
							sub_user_name = sub_user.name
							flair = next(subreddit.flair(sub_user)).get("flair_text")
							if (flair[:6] == "SILVER") or (flair[:4] == "GOLD"):
								delete_submission.mod.remove()
								comment = submission.reply("The use of this privilege has been approved as you have enough subreddit points (" + str(SILVER_POINTS_THRESHOLD) + ").\n\nPost " + delete_submission_id + " (" + delete_submission_title + ") has been deleted.")
								comment.mod.distinguish(how="yes")
								log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Approved deletion of post " + delete_submission_id + " (" + delete_submission_title + ") by u/" + sub_user_name + ".")
							else:
								comment = submission.reply("Error: You do not have enough subreddit points (" + str(SILVER_POINTS_THRESHOLD) + ") to delete posts.")
								comment.mod.distinguish(how="yes")
								log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Denied deletion of post " + delete_submission_id + " (" + delete_submission_title + ") by u/" + sub_user_name + ".")
						else:
							comment = submission.reply("Error: The specified post is already deleted.")
							comment.mod.distinguish(how="yes")
					else:
						comment = submission.reply("Error: The specified post is not in this subreddit.")
						comment.mod.distinguish(how="yes")
				except (TypeError, ValueError):
					comment = submission.reply("Error: You must specify the post that you would like to delete.")
					comment.mod.distinguish(how="yes")
				except (prawcore.exceptions.BadRequest, prawcore.exceptions.NotFound):
					comment = submission.reply("Error: The specified post does not exist.")
					comment.mod.distinguish(how="yes")
				except (prawcore.exceptions.Forbidden, praw.exceptions.APIException):
					comment = submission.reply("Error: The specified post cannot be deleted.")
					comment.mod.distinguish(how="yes")
			elif submission_is_self and submission_title_lower[:14] == "ban privilege:":
				try:
					ban_user = reddit.redditor(name=submission_title[15:])
					exception_test = ban_user.fullname
					ban_user_name = ban_user.name
					if ban_user_name not in moderator_user_names:
						if ban_user_name not in banned_user_names:
							sub_user = submission.author
							sub_user_name = sub_user.name
							flair = next(subreddit.flair(sub_user)).get("flair_text")
							if flair[:4] == "GOLD":
								subreddit.banned.add(redditor=ban_user, ban_reason="You have been banned by a GOLD member of r/" + subreddit_name + ".")
								comment = submission.reply("The use of this privilege has been approved as you have enough subreddit points (" + str(GOLD_POINTS_THRESHOLD) + ").\n\nu/" + ban_user_name + " has been banned.")
								comment.mod.distinguish(how="yes")
								log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Approved banning of u/" + ban_user_name + " by u/" + sub_user_name + ".")
							else:
								comment = submission.reply("Error: You do not have enough subreddit points (" + str(GOLD_POINTS_THRESHOLD) + ") to ban users.")
								comment.mod.distinguish(how="yes")
								log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Denied banning of u/" + ban_user_name + " by u/" + sub_user_name + ".")
						else:
							comment = submission.reply("Error: The specified user is already banned.")
							comment.mod.distinguish(how="yes")
					else:
						comment = submission.reply("Error: The specified user cannot be banned as they are a moderator.")
						comment.mod.distinguish(how="yes")
				except (TypeError, ValueError):
					comment = submission.reply("Error: You must specify the user that you would like to ban.")
					comment.mod.distinguish(how="yes")
				except (prawcore.exceptions.BadRequest, prawcore.exceptions.NotFound):
					comment = submission.reply("Error: The specified user does not exist.")
					comment.mod.distinguish(how="yes")
				except (prawcore.exceptions.Forbidden, praw.exceptions.APIException):
					comment = submission.reply("Error: The specified user cannot be banned.")
					comment.mod.distinguish(how="yes")
			elif submission_is_self and submission_title_lower[:9] == "ban poll:":
				try:
					ban_user = reddit.redditor(name=submission_title[10:])
					exception_test = ban_user.fullname
					ban_user_name = ban_user.name
					if ban_user_name not in moderator_user_names:
						if ban_user_name not in banned_user_names:
							sub_user_name = submission.author.name
							open_ban_polls.append((submission_id, ban_user_name))
							comment = submission.reply("This ban poll has been approved.\n\nReply \"yes\" is you think that u/" + ban_user_name + " should be banned, or reply \"no\" if you think that u/" + ban_user_name + " should not be banned.\n\nThe results will be automatically calculated and applied after " + str(POLL_TIME_HOURS) + " hour(s).")
							comment.mod.distinguish(how="yes")
							log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Approved ban poll for u/" + ban_user_name + ", created by u/" + sub_user_name + ".")
						else:
							comment = submission.reply("Error: The specified user is already banned.")
							comment.mod.distinguish(how="yes")
					else:
						comment = submission.reply("Error: The specified user cannot be banned as they are a moderator.")
						comment.mod.distinguish(how="yes")
				except (TypeError, ValueError):
					comment = submission.reply("Error: You must specify the user that you would like to be banned.")
					comment.mod.distinguish(how="yes")
				except (prawcore.exceptions.BadRequest, prawcore.exceptions.NotFound):
					comment = submission.reply("Error: The specified user does not exist.")
					comment.mod.distinguish(how="yes")
			elif submission_is_self and submission_title_lower[:15] == "moderator poll:":
				try:
					mod_user = reddit.redditor(name=submission_title[16:])
					exception_test = mod_user.fullname
					mod_user_name = mod_user.name
					if mod_user_name not in moderator_user_names:
						if mod_user_name not in banned_user_names:
							sub_user_name = submission.author.name
							open_mod_polls.append((submission_id, mod_user_name))
							comment = submission.reply("This moderator poll has been approved.\n\nReply \"yes\" is you think that u/" + mod_user_name + " should become a moderator, or reply \"no\" if you think that u/" + mod_user_name + " should not become a moderator.\n\nThe results will be automatically calculated and applied after " + str(POLL_TIME_HOURS) + " hour(s).")
							comment.mod.distinguish(how="yes")
							log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Approved moderator poll for u/" + mod_user_name + ", created by u/" + sub_user_name + ".")
						else:
							comment = submission.reply("Error: The specified user cannot become a moderator as they are banned.")
							comment.mod.distinguish(how="yes")
					else:
						comment = submission.reply("Error: The specified user is already a moderator.")
						comment.mod.distinguish(how="yes")
				except (TypeError, ValueError):
					comment = submission.reply("Error: You must specify the user that you would like to become a moderator.")
					comment.mod.distinguish(how="yes")
				except (prawcore.exceptions.BadRequest, prawcore.exceptions.NotFound):
					comment = submission.reply("Error: The specified user does not exist.")
					comment.mod.distinguish(how="yes")
			elif submission_is_self and submission_title_lower[:11] == "title poll:":
				subreddit_title = submission_title[12:]
				if 1 <= len(subreddit_title) <= 100:
					sub_user_name = submission.author.name
					open_title_polls.append((submission_id, subreddit_title))
					comment = submission.reply("This subreddit title poll has been approved.\n\nReply \"yes\" is you think that \"" + subreddit_title + "\" should be the new subreddit title, or reply \"no\" if you think that \"" + subreddit_title + "\" should not be the new subreddit title.\n\nThe results will be automatically calculated and applied after " + str(POLL_TIME_HOURS) + " hour(s).")
					comment.mod.distinguish(how="yes")
					log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Approved subreddit title poll for \"" + subreddit_title + "\", created by u/" + sub_user_name + ".")
				elif len(subreddit_title) == 0:
					comment = submission.reply("Error: You must specify the subreddit title that you would like to be used.")
					comment.mod.distinguish(how="yes")
				else:
					comment = submission.reply("Error: The specified subreddit title is too long. It must 100 characters or fewer.")
					comment.mod.distinguish(how="yes")
			elif submission_is_self and submission_title_lower[:15] == "subreddit fork:":
				new_subreddit_name = submission_title[16:]
				if VALID_SUBREDDIT_NAME_REGEX.match(new_subreddit_name):
					try:
						new_subreddit = reddit.subreddit.create(name=new_subreddit_name)
						new_subreddit_name = new_subreddit.display_name
						sub_user = submission.author
						sub_user_name = sub_user.display_name
						new_subreddit.moderator.add(redditor=sub_user)
						comment = submission.reply("This subreddit fork has been approved.\n\nThe new subreddit is available at r/" + new_subreddit_name + ".")
						comment.mod.distinguish(how="yes")
						log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Approved subreddit fork r/" + new_subreddit_name + ", created by u/" + sub_user_name + ".")
						try:
							for top_submission in subreddit.top(limit=TOP_POSTS_TO_FORK):
								if top_submission.is_self:
									new_subreddit.submit(title="[FORKED] " + top_submission.title, selftext=top_submission.selftext)
								else:
									new_subreddit.submit(title="[FORKED] " + top_submission.title, url=top_submission.url)
							comment = submission.reply("The top posts from this subreddit have been re-posted in the subreddit fork.")
							comment.mod.distinguish(how="yes")
							log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Re-posted top posts from this subreddit in subreddit fork r/" + new_subreddit_name + ".")
						except praw.exceptions.APIException:
							comment = submission.reply("Error: The top posts from this subreddit could not be re-posted in the subreddit fork.")
							comment.mod.distinguish(how="yes")
							log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not re-post top posts from this subreddit in subreddit fork r/" + new_subreddit_name + ".")
					except praw.exceptions.APIException:
						comment = submission.reply("Error: The subreddit fork could not be created. The specified subreddit name may already be in use, or GovernanceBot may be unable to create a new subreddit at this time.")
						comment.mod.distinguish(how="yes")
				elif len(new_subreddit_name) == 0:
					comment = submission.reply("Error: You must specify the subreddit fork name.")
					comment.mod.distinguish(how="yes")
				else:
					comment = submission.reply("Error: The specified subreddit fork name is not valid. It must be between 2 and 21 characters long, and only contain letters, numbers, and underscores (but must not start with an underscore).")
					comment.mod.distinguish(how="yes")
			else:
				comment = submission.reply("If you would like to delete this post, reply \"delete\".\n\nIf this comment has at least " + str(DELETE_REPLIES_THRESHOLD) + " delete replies after " + str(POLL_TIME_HOURS) + " hour(s), the post will be deleted.")
				comment.mod.distinguish(how="yes")
				open_delete_comments.append((comment.id, submission_id, submission_title))

closed_polls = []
for ban_poll in open_ban_polls:
	submission_id = ban_poll[0]
	ban_user_name = ban_poll[1]
	if ban_user_name not in moderator_user_names:
		if ban_user_name not in banned_user_names:
			try:
				submission = reddit.submission(id=submission_id)
				exception_test = submission.comments
				ban_user = reddit.redditor(name=ban_user_name)
				exception_test = ban_user.fullname
				if submission.selftext != "[deleted]":
					if current_unix_timestamp - int(submission.created_utc) >= POLL_TIME_SECONDS:
						poll_yes = poll(submission)
						if poll_yes:
							subreddit.banned.add(redditor=ban_user, ban_reason="You have been banned as a result of a poll within r/" + subreddit_name + ".")
							comment = submission.reply("This ban poll is now closed.\n\nThere were more \"yes\" votes than \"no\" votes, so u/" + ban_user_name + " has been banned.")
							comment.mod.distinguish(how="yes")
							log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Banned u/" + ban_user_name + " after poll.")
						else:
							comment = submission.reply("This ban poll is now closed.\n\nThere were more \"no\" votes than \"yes\" votes (or an equal number), so u/" + ban_user_name + " has not been banned.")
							comment.mod.distinguish(how="yes")
							log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Did not ban u/" + ban_user_name + " after poll.")
						closed_polls.append(ban_poll)
				else:
					closed_polls.append(ban_poll)
			except (prawcore.exceptions.Forbidden, praw.exceptions.APIException):
				closed_polls.append(ban_poll)
				comment = submission.reply("Error: This ban poll could not be completed.")
				comment.mod.distinguish(how="yes")
				log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete ban poll for u/" + ban_user_name + ".")
		else:
			closed_polls.append(ban_poll)
			comment = submission.reply("Error: This ban poll could not be completed as the specified user is a moderator.")
			comment.mod.distinguish(how="yes")
			log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete ban poll for u/" + ban_user_name + ".")
	else:
		closed_polls.append(ban_poll)
		comment = submission.reply("Error: This ban poll could not be completed as the specified user is already banned.")
		comment.mod.distinguish(how="yes")
		log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete ban poll for u/" + ban_user_name + ".")
for closed_poll in closed_polls:
	open_ban_polls.remove(closed_poll)

closed_polls = []
for mod_poll in open_mod_polls:
	submission_id = mod_poll[0]
	mod_user_name = mod_poll[1]
	if mod_user_name not in moderator_user_names:
		if mod_user_name not in banned_user_names:
			try:
				submission = reddit.submission(id=submission_id)
				exception_test = submission.comments
				mod_user = reddit.redditor(name=mod_user_name)
				exception_test = mod_user.fullname
				if submission.selftext != "[deleted]":
					if current_unix_timestamp - int(submission.created_utc) >= POLL_TIME_SECONDS:
						poll_yes = poll(submission)
						if poll_yes:
							subreddit.moderator.add(redditor=mod_user)
							comment = submission.reply("This moderator poll is now closed.\n\nThere were more \"yes\" votes than \"no\" votes, so u/" + mod_user_name + " has been promoted to moderator.")
							comment.mod.distinguish(how="yes")
							log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Promoted u/" + mod_user_name + " to moderator after poll.")
						else:
							comment = submission.reply("This moderator poll is now closed.\n\nThere were more \"no\" votes than \"yes\" votes (or an equal number), so u/" + mod_user_name + " has not been promoted to moderator.")
							comment.mod.distinguish(how="yes")
							log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Did not promote u/" + mod_user_name + " to moderator after poll.")
						closed_polls.append(mod_poll)
				else:
					closed_polls.append(mod_poll)
					log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete moderator poll for u/" + mod_user_name + ".")
			except (prawcore.exceptions.Forbidden, praw.exceptions.APIException):
				closed_polls.append(mod_poll)
				comment = submission.reply("Error: This moderator poll could not be completed.")
				comment.mod.distinguish(how="yes")
				log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete moderator poll for u/" + mod_user_name + ".")
		else:
			closed_polls.append(mod_poll)
			comment = submission.reply("Error: This moderator poll could not be completed as the specified user is already a moderator.")
			comment.mod.distinguish(how="yes")
			log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete moderator poll for u/" + mod_user_name + ".")
	else:
		closed_polls.append(mod_poll)
		comment = submission.reply("Error: This moderator poll could not be completed as the specified user is banned.")
		comment.mod.distinguish(how="yes")
		log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete moderator poll for u/" + mod_user_name + ".")
for closed_poll in closed_polls:
	open_mod_polls.remove(closed_poll)

closed_polls = []
for title_poll in open_title_polls:
	submission_id = title_poll[0]
	subreddit_title = title_poll[1]
	try:
		submission = reddit.submission(id=submission_id)
		exception_test = submission.comments
		if submission.selftext != "[deleted]":
			if current_unix_timestamp - int(submission.created_utc) >= POLL_TIME_SECONDS:
				poll_yes = poll(submission)
				if poll_yes:
					subreddit.mod.update(title=subreddit_title)
					comment = submission.reply("This subreddit title poll is now closed.\n\nThere were more \"yes\" votes than \"no\" votes, so \"" + subreddit_title + "\" has been approved as the new subreddit title.")
					comment.mod.distinguish(how="yes")
					log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Approved new subreddit title \"" + subreddit_title + "\" after poll.")
				else:
					comment = submission.reply("This subreddit title poll is now closed.\n\nThere were more \"no\" votes than \"yes\" votes (or an equal number), so \"" + subreddit_title + "\" has not been approved as the new subreddit title.")
					comment.mod.distinguish(how="yes")
					log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Did not approve new subreddit title \"" + subreddit_title + "\" after poll.")
				closed_polls.append(title_poll)
		else:
			closed_polls.append(title_poll)
			log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete subreddit title poll for \"" + subreddit_title + "\".")
	except praw.exceptions.APIException:
		closed_polls.append(title_poll)
		comment = submission.reply("Error: This subreddit title poll could not be completed.")
		comment.mod.distinguish(how="yes")
		log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not complete subreddit title poll for \"" + subreddit_title + "\".")
for closed_poll in closed_polls:
	open_title_polls.remove(closed_poll)

closed_delete_comments = []
for delete_comment in open_delete_comments:
	comment_id = delete_comment[0]
	submission_id = delete_comment[1]
	submission_title = delete_comment[2]
	try:
		comment = reddit.comment(id=comment_id).refresh()
		submission = reddit.submission(id=submission_id)
		exception_test = submission.comments
		if submission.selftext != "[deleted]":
			if current_unix_timestamp - int(submission.created_utc) >= POLL_TIME_SECONDS:
				delete_users = []
				delete_reply_count = 0
				for reply in comment.replies:
					if isinstance(reply, praw.models.MoreComments):
						continue
					if reply.body.lower()[:6] == "delete":
						if reply.author.name not in delete_users:
							delete_reply_count += 1
							delete_users.append(reply.author.name)
				if delete_reply_count >= DELETE_REPLIES_THRESHOLD:
					submission.mod.remove()
					log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Deleted post " + submission_id + " (" + submission_title + ") after counting delete replies.")
				else:
					comment.reply("The window in which delete replies can be posted is now closed.\n\nThere were fewer than " + str(DELETE_REPLIES_THRESHOLD) + " delete replies, so the post has not been deleted.")
					comment.mod.distinguish(how="yes")
				closed_delete_comments.append(delete_comment)
		else:
			closed_delete_comments.append(delete_comment)
	except (praw.exceptions.PRAWException, praw.exceptions.APIException):
		closed_delete_comments.append(delete_comment)
		comment = submission.reply("Error: The delete replies count could not be completed.")
		comment.mod.distinguish(how="yes")
		log.edit(log.selftext + "\n\n" + current_formatted_timestamp + " - Could not count delete replies for post " + submission_id + " (" + submission_title + ").")
for closed_delete_comment in closed_delete_comments:
	open_delete_comments.remove(closed_delete_comment)

with open("data/guide_log.pkl", "wb") as guide_log_file:
	pickle.dump((guide_id, log_id), guide_log_file)
with open("data/posts.pkl", "wb") as posts_file:
	pickle.dump(posts, posts_file)
with open("data/open_ban_polls.pkl", "wb") as open_ban_polls_file:
	pickle.dump(open_ban_polls, open_ban_polls_file)
with open("data/open_mod_polls.pkl", "wb") as open_mod_polls_file:
	pickle.dump(open_mod_polls, open_mod_polls_file)
with open("data/open_title_polls.pkl", "wb") as open_title_polls_file:
	pickle.dump(open_title_polls, open_title_polls_file)
with open("data/open_delete_comments.pkl", "wb") as open_delete_comments_file:
	pickle.dump(open_delete_comments, open_delete_comments_file)
