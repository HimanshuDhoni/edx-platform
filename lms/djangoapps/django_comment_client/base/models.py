import datetime

from mongoengine import Document, EmbeddedDocument
from mongoengine.fields import BooleanField, DateTimeField, DictField, EmbeddedDocumentField, IntField, ListField, ReferenceField, StringField


class Content(Document):

    meta = {'allow_inheritance': True, 'collection': 'contents'}
    #include Mongo::Voteable

    visible = BooleanField(default=True)
    abuse_flaggers = ListField(default=[])
    historical_abuse_flaggers = ListField(default=[]) #preserve abuse flaggers after a moderator unflags)
    author_username = StringField(default=None)

    author = ReferenceField('User')
    #before_save :set_username
    def set_username(self):
        # avoid having to look this attribute up later, since it does not change
        self.author_username = self.author.username

    def author_with_anonymity(self, attr=None, attr_when_anonymous=None):
        if not attr:
            if self.anonymous or self.anonymous_to_peers:
                return None
            else:
                return self.author
        else:
            if self.anonymous or self.anonymous_to_peers:
                return attr_when_anonymous
            else:
                return getattr(self.author, attr)



class Thread(Content):

    #include Mongoid::Timestamps
    #extend Enumerize

    #voteable self, :up => +1, :down => -1

    thread_type = StringField(default="discussion")
    #enumerize :thread_type, in: [:question, :discussion]
    comment_count = IntField(default=0)
    title = StringField()
    body = StringField()
    course_id = StringField()
    commentable_id = StringField()
    anonymous = BooleanField(default=False)
    anonymous_to_peers = BooleanField(default=False)
    closed = BooleanField(default=False)
    at_position_list = ListField(default=[])
    last_activity_at = DateTimeField(default=datetime.datetime.utcnow)
    group_id = IntField()
    pinned = BooleanField()

    #index({author_id: 1, course_id: 1})


    author = ReferenceField('User')
    comments = ListField(ReferenceField('Comment'))
    #belongs_to :author, class_name: "User", inverse_of: :comment_threads, index: true#, autosave: true
    #has_many :comments, dependent: :destroy#, autosave: true# Use destroy to envoke callback on the top-level comments TODO async
    #has_many :activities, autosave: true

    #attr_accessible :title, :body, :course_id, :commentable_id, :anonymous, :anonymous_to_peers, :closed, :thread_type

    #validates_presence_of :thread_type
    #validates_presence_of :title
    #validates_presence_of :body
    #validates_presence_of :course_id # do we really need this?
    #validates_presence_of :commentable_id
    #validates_presence_of :author, autosave: false

    #before_create :set_last_activity_at
    #before_update :set_last_activity_at, :unless => lambda { closed_changed? }
    #after_update :clear_endorsements

    #before_destroy :destroy_subscriptions

    #scope :active_since, ->(from_time) { where(:last_activity_at => {:$gte => from_time}) }

    #def root_comments
    #    Comment.roots.where(comment_thread_id: self.id)


    #def commentable
    #    Commentable.find(commentable_id)


    #def subscriptions
    #    Subscription.where(source_id: id.to_s, source_type: self.class.to_s)


    #def subscribers
    #    subscriptions.map(&:subscriber)


    #def endorsed
    #    comments.where(endorsed: true).exists?


    def to_dict(self, params={}):
        hash = self.to_mongo().to_dict()
        hash = {k: hash[k] for k in ' '.split("thread_type title body course_id anonymous anonymous_to_peers commentable_id created_at updated_at at_position_list closed")}
        hash.update({
            "id": self._id,
            "user_id": self.author_id,
            "username": self.author_username,
            "votes": None,  # votes.slice(*%w[count up_count down_count point]),
            "abuse_flaggers": self.abuse_flaggers,
            "tags": [],
            "type": "thread",
            "group_id": self.group_id,
            "pinned": self.pinned,
            "comments_count": self.comment_count
        })

    @property
    def comment_thread_id(self):
        #so that we can use the comment thread id as a common attribute for flagging
        return self.id


    def set_last_activity_at(self):
        self.last_activity_at = datetime.datetime.utcnow()


    def clear_endorsements(self):
        #if self.thread_type_changed?
        # We use 'set' instead of 'update_attributes' because the Comment model has a 'before_update' callback that sets
        # the last activity time on the thread. Therefore the callbacks would be mutually recursive and we end up with a
        # 'SystemStackError'. The 'set' method skips callbacks and therefore bypasses this issue.
        for comment in self.comments:
            comment.endorsed = False
            comment.endorsement = None



class Comment(Content):

    #include Mongoid::Tree
    #include Mongoid::Timestamps
    #include Mongoid::MagicCounterCache

    #voteable self, :up => +1, :down => -1

    course_id = StringField()
    body = StringField()
    endorsed = BooleanField(default=False)
    endorsement = DictField()
    anonymous = BooleanField(default=False)
    anonymous_to_peers = BooleanField(default=False)
    at_position_list = ListField(default=[])

    #index({author_id: 1, course_id: 1})
    #index({_type: 1, comment_thread_id: 1, author_id: 1, updated_at: 1})

    sk = StringField(default=None)
    #before_save :set_sk
    def set_sk(self):
        # this attribute is explicitly write-once
        if self.sk is None:
            self.sk = "-".join(self.parent_ids.copy() + self.id)

    thread = ReferenceField('Thread')
    #belongs_to :comment_thread, index: true
    #belongs_to :author, class_name: "User", index: true

    #attr_accessible :body, :course_id, :anonymous, :anonymous_to_peers, :endorsed, :endorsement

    #validates_presence_of :comment_thread, autosave: false
    #validates_presence_of :body
    #validates_presence_of :course_id
    #validates_presence_of :author, autosave: false

    #counter_cache :comment_thread

    #before_destroy :destroy_children # TODO async

    #before_create :set_thread_last_activity_at
    #before_update :set_thread_last_activity_at

    @classmethod
    def hash_tree(cls, nodes):
        #nodes.map{|node, sub_nodes| node.to_hash.merge("children" => hash_tree(sub_nodes).compact)}
        raise NotImplementedError

    # This should really go somewhere else, but sticking it here for now. This is
    # used to flatten out the subtree fetched by calling self.subtree. This is
    # equivalent to calling descendants_and_self; however, calling
    # descendants_and_self and subtree both is very inefficient. It's cheaper to
    # just flatten out the subtree, and simpler than duplicating the code that
    # actually creates the subtree.
    @classmethod
    def flatten_subtree(cls, x):
        raise NotImplementedError
        #if x.is_a? Array
        #    x.flatten.map{|y| self.flatten_subtree(y)}
        #elif x.is_a? Hash
        #    x.to_a.map{|y| self.flatten_subtree(y)}.flatten
        #else
        #    x


    def to_dict(self, params={}):
        raise NotImplementedError
        #sort_by_parent_and_time = Proc.new do |x, y|
        #arr_cmp = x.parent_ids.map(&:to_s) <=> y.parent_ids.map(&:to_s)
        #if arr_cmp != 0
        #arr_cmp
        #else
        #x.created_at <=> y.created_at
        #
        #if params[:recursive]
        ## TODO: remove and reuse the new hierarchical sort keys if possible
        #subtree_hash = subtree(sort: sort_by_parent_and_time)
        #self.class.hash_tree(subtree_hash).first
        #else
        #as_document.slice(*%w[body course_id endorsed endorsement anonymous anonymous_to_peers created_at updated_at at_position_list])
        #.merge("id" => _id)
        #.merge("user_id" => author_id)
        #.merge("username" => author_username)
        #.merge("depth" => depth)
        #.merge("closed" => comment_thread is None ? false : comment_thread.closed) # ditto
        #.merge("thread_id" => comment_thread_id)
        #.merge("commentable_id" => comment_thread is None ? None : comment_thread.commentable_id) # ditto
        #.merge("votes" => votes.slice(*%w[count up_count down_count point]))
        #.merge("abuse_flaggers" => abuse_flaggers)
        #.merge("type" => "comment")

    @property
    def commentable_id(self):
        raise NotImplementedError
        ##we need this to have a universal access point for the flag rake task
        #if self.comment_thread_id
        #t = CommentThread.find self.comment_thread_id
        #if t
        #t.commentable_id
        #
        #rescue Mongoid::Errors::DocumentNotFound
        #None

    @property
    def group_id(self):
        raise NotImplementedError
        #if self.comment_thread_id
        #t = CommentThread.find self.comment_thread_id
        #if t
        #t.group_id
        #
        #rescue Mongoid::Errors::DocumentNotFound
        #None

    @classmethod
    def by_date_range_and_thread_ids(cls, from_when, to_when, thread_ids):
        raise NotImplementedError
        #return all content between from_when and to_when
        #self.where(:created_at.gte => (from_when)).where(:created_at.lte => (to_when)).
        #where(:comment_thread_id.in => thread_ids)


    def set_thread_last_activity_at(self):
        raise NotImplementedError
        #self.comment_thread.update_attributes!(last_activity_at: Time.now.utc)



class User(Document):

    meta = {'collection': 'users'}
    #include Mongo::Voter

    external_id = StringField(primary_key=True)
    username = StringField()
    default_sort_key = StringField(default="date")

    comments = ListField(ReferenceField('Comment'))
    threads = ListField(ReferenceField('Thread'))
    read_states = ListField(EmbeddedDocumentField('ReadState'))
    #has_many :comments, inverse_of: :author
    #has_many :comment_threads, inverse_of: :author
    #has_many :activities, class_name: "Notification", inverse_of: :actor
    #has_and_belongs_to_many :notifications, inverse_of: :receivers

    #validates_presence_of :external_id
    #validates_presence_of :username
    #validates_uniqueness_of :external_id
    #validates_uniqueness_of :username

    #index( {external_id: 1}, {unique: true, background: true} )

    @classmethod
    def from_django_user(cls, user, course_id=None):
        """
        """
        obj, __ = cls.objects.get_or_create(
            external_id=str(user.id),
            username=user.username,
        )
        if course_id:
            setattr(obj, 'course_id', course_id)
        return obj

    def follow(self, thread):
        """
        """
        #if source._id == self._id and source.class == self.class
        #  raise ArgumentError, "Cannot follow oneself"
        #else
        #  Subscription.find_or_create_by(subscriber_id: self._id.to_s, source_id: source._id.to_s, source_type: source.class.to_s)
        #end
        #assert isinstance(thread, Thread)
        Subscription.objects.get_or_create(
            subscriber_id=self.id,
            source_id=thread.id,
            source_type="Thread"
        )

    def unfollow(self, thread):
        """
        """
        # subscription = Subscription.where(subscriber_id: self._id.to_s, source_id: source._id.to_s, source_type: source.class.to_s).first
        # subscription.destroy if subscription
        # subscription
        Subscription.objects(
            subscriber_id=self.id,
            source_id=thread.id,
            source_type="Thread",
        ).delete()

    @property
    def subscriptions_as_source(self):
        raise NotImplementedError
        #Subscription.where(source_id: id.to_s, source_type: self.class.to_s)

    @property
    def subscribed_thread_ids(self):
        #raise NotImplementedError
        subs = Subscription.objects(
            subscriber_id=self.id,
            source_type="Thread"
        )
        return [doc.source_id for doc in subs]

    @property
    def subscribed_threads(self):
        raise NotImplementedError
        #CommentThread.in({"_id" => subscribed_thread_ids})


    def to_dict(self, params={}):
        course_id = params.get('course_id', getattr(self, 'course_id', None))
        #hash = as_document.slice(*%w[username external_id])
        hash = {
            "username": self.username,
            "external_id": self.external_id
        }
        #if params[:complete]
        if params.get('complete', True):
            #hash = hash.merge("subscribed_thread_ids" => subscribed_thread_ids,
            #                "subscribed_commentable_ids" => [], # not used by comment client.  To be removed once removed from comment client.
            #                "subscribed_user_ids" => [], # ditto.
            #                "follower_ids" => [], # ditto.
            #                "id" => id,
            #                "upvoted_ids" => upvoted_ids,
            #                "downvoted_ids" => downvoted_ids,
            #                "default_sort_key" => default_sort_key
            #               )
            hash.update({
                "subscribed_thread_ids": self.subscribed_thread_ids,
                "id": self.id,
                "upvoted_ids": self.upvoted_ids,
                "downvoted_ids": self.downvoted_ids,
                "default_sort_key": self.default_sort_key,
            })
        #
        #if params[:course_id]
        if course_id:
            #self.class.trace_execution_scoped(['Custom/User.to_hash/count_comments_and_threads']) do
            #if not params[:group_ids].empty?
            if params.get('group_ids'):
                #  # Get threads in either the specified group(s) or posted to all groups (None).
                #  specified_groups_or_global = params[:group_ids] << None
                #  threads_count = CommentThread.where(
                #    author_id: id,
                #    course_id: params[:course_id],
                #    group_id: {"$in" => specified_groups_or_global},
                #    anonymous: false,
                #    anonymous_to_peers: false
                #  ).count
                threads = Thread.objects(
                    author=self,
                    course_id=unicode(course_id),
                    group_id__in=params['group_ids'] + [None],
                    anonymous=False,
                    anonymous_to_peers=False,
                )
                threads_count = len(list(threads))

                #
                #  # Note that the comments may have been responses to a thread not started by author_id.
                #  comment_thread_ids = Comment.where(
                #    author_id: id,
                #    course_id: params[:course_id],
                #    anonymous: false,
                #    anonymous_to_peers: false
                #  ).collect{|c| c.comment_thread_id}
                comments = Comment.objects(
                    author=self,
                    course_id=unicode(course_id),
                    anonymous=False,
                    anonymous_to_peers=False,
                )
                comment_thread_ids = set(list(doc.comment_thread_id for doc in comments))

                #  # Filter to the unique thread ids visible to the specified group(s).
                #  group_comment_thread_ids = CommentThread.where(
                #    id: {"$in" => comment_thread_ids.uniq},
                #    group_id: {"$in" => specified_groups_or_global},
                #  ).collect{|d| d.id}
                group_visible_threads = Thread.objects(
                    id__in=comment_thread_ids,
                    group_id__in=params['group_ids'] + [None]
                )
                group_visible_thread_ids = set(list(doc.id for doc in group_visible_threads))
                #
                #  # Now filter comment_thread_ids so it only includes things in group_comment_thread_ids
                #  # (keeping duplicates so the count will be correct).
                #  comments_count = comment_thread_ids.count{
                #    |comment_thread_id| group_comment_thread_ids.include?(comment_thread_id)
                #  }
                #
                comments_count = 0
                for comment_thread_id in comment_thread_ids:
                    if comment_thread_id in group_visible_thread_ids:
                        comments_count += 1

            else:
                #  threads_count = CommentThread.where(
                #    author_id: id,
                #    course_id: params[:course_id],
                #    anonymous: false,
                #    anonymous_to_peers: false
                #  ).count
                threads = Thread.objects(
                    author=self,
                    course_id=unicode(course_id),
                    anonymous=False,
                    anonymous_to_peers=False,
                )
                print 'threads', list(threads)
                threads_count = len(list(threads))
                #  comments_count = Comment.where(
                #    author_id: id,
                #    course_id: params[:course_id],
                #    anonymous: false,
                #    anonymous_to_peers: false
                #  ).count
                comments = Comment.objects(
                    author=self,
                    course_id=unicode(course_id),
                    anonymous=False,
                    anonymous_to_peers=False,
                )
                comments_count = len(list(comments))
            #
            #hash = hash.merge("threads_count" => threads_count, "comments_count" => comments_count)
            hash.update({
                "threads_count": threads_count,
                "comments_count": comments_count,
            })
            #
        #hash
        return hash

    @property
    def upvoted_ids(self):
        #raise NotImplementedError
        return []
        #Content.up_voted_by(self).map(&:id)


    @property
    def downvoted_ids(self):
        #raise NotImplementedError
        return []
        #Content.down_voted_by(self).map(&:id)


    @property
    def followers(self):
        raise NotImplementedError
        #subscriptions_as_source.map(&:subscriber)


    def subscribe(self, source):
        raise NotImplementedError
        #if source._id == self._id and source.class == self.class
        #    raise ArgumentError, "Cannot follow oneself"
        #else
        #    Subscription.find_or_create_by(subscriber_id: self._id.to_s, source_id: source._id.to_s, source_type: source.class.to_s)

    def unsubscribe(self, source):
        raise NotImplementedError
        #subscription = Subscription.where(subscriber_id: self._id.to_s, source_id: source._id.to_s, source_type: source.class.to_s).first
        #subscription.destroy if subscription
        #subscription

    def mark_as_read(self, thread):
        raise NotImplementedError
        #read_state = read_states.find_or_create_by(course_id: thread.course_id)
        #read_state.last_read_times[thread.id.to_s] = Time.now.utc
        #read_state.save

    def active_threads(self, query_params={}):
        # raise NotImplementedError
        #  page = (params["page"] || DEFAULT_PAGE).to_i
        #  per_page = (params["per_page"] || DEFAULT_PER_PAGE).to_i
        #  per_page = DEFAULT_PER_PAGE if per_page <= 0
        #
        #  active_contents = Content.where(author_id: user_id, anonymous: false, anonymous_to_peers: false, course_id: params["course_id"])
        #                           .order_by(updated_at: :desc)
        #
        #  # Get threads ordered by most recent activity, taking advantage of the fact
        #  # that active_contents is already sorted that way
        #  active_thread_ids = active_contents.inject([]) do |thread_ids, content|
        #    thread_id = content._type == "Comment" ? content.comment_thread_id : content.id
        #    thread_ids << thread_id if not thread_ids.include?(thread_id)
        #    thread_ids
        #  end
        #
        #  threads = CommentThread.in({"_id" => active_thread_ids})
        #
        #  group_ids = get_group_ids_from_params(params)
        #  if not group_ids.empty?
        #    threads = get_group_id_criteria(threads, group_ids)
        #  end
        #
        #  num_pages = [1, (threads.count / per_page.to_f).ceil].max
        #  page = [num_pages, [1, page].max].min
        #
        #  sorted_threads = threads.sort_by {|t| active_thread_ids.index(t.id)}
        #  paged_threads = sorted_threads[(page - 1) * per_page, per_page]
        #
        #  presenter = ThreadListPresenter.new(paged_threads, user, params[:course_id])
        #  collection = presenter.to_hash
        #
        #  json_output = nil
        #  self.class.trace_execution_scoped(['Custom/get_user_active_threads/json_serialize']) do
        #    json_output = {
        #      collection: collection,
        #      num_pages: num_pages,
        #      page: page,
        #    }.to_json
        #  end
        #  json_output
        #
        #
        #
        #
        # url = _url_for_user_active_threads(self.id)
        # params = {'course_id': self.course_id.to_deprecated_string()}
        # params = merge_dict(params, query_params)
        # response = perform_request(
        #     'get',
        #     url,
        #     params,
        #     metric_action='user.active_threads',
        #     metric_tags=self._metric_tags,
        #     paged_results=True,
        # )
        # return response.get('collection', []), response.get('page', 1), response.get('num_pages', 1)
        return [], 1, 1




class ReadState(EmbeddedDocument):

    course_id = StringField()
    last_read_times = DictField(default={})
    #embedded_in :user

    #validates :course_id, uniqueness: true, presence: true

    def to_dict(self):
        return self.to_mongo().to_dict()


class Subscription(Document):
    #include Mongoid::Timestamps

    meta = {'collection': 'subscriptions'}

    subscriber_id = StringField()
    source_id = StringField()
    source_type = StringField()

    def to_dict(self):
        return {
            "subscriber_id": self.subscriber_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
        }

    @property
    def subscriber(self):
        return User.objects.get(self.subscriber_id)

    @property
    def source(self):
        return {
            "Thread": Thread,
            "Comment": Comment,
        }[self.source_type].get(self.source_id)


if __name__=='__main__':

    # host OS
    from mongoengine import connect
    cx = connect('cs_comments_service_development', host='localhost:27018')

else:

    # devstack
    from mongoengine import connect
    cx = connect('cs_comments_service_development')