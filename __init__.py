from datetime import datetime

from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_workshop.intents import IntentBuilder
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills import OVOSSkill

from lingua_franca.format import pronounce_number, nice_date, nice_number
from lingua_franca.util import fuzzy_match

from tmdbv3api import TMDb, Movie, Person


class MovieMaster(OVOSSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(
            internet_before_load=True,
            network_before_load=True,
            gui_before_load=False,
            requires_internet=True,
            requires_network=True,
            requires_gui=False,
            no_internet_fallback=False,
            no_network_fallback=False,
            no_gui_fallback=True,
        )

    def initialize(self):
        DEFAULT_SETTINGS = {
            "apiv3": self.settings.get("apiv3", "8a2e8882b465b1cf7cce9ff6b35bdd7e"),
            "search_depth": self.settings.get("search_depth", 5),
            "match_confidence": self.settings.get("match_confidence", 0.8)
        }
        self.settings.merge(DEFAULT_SETTINGS, new_only=False)

        self._api_key = self.verify_api(self.settings.get("apiv3"))
        self._search_depth = self.settings.get("search_depth")
        self._match_confidence = self.settings.get("match_confidence")

        self._active_movie = None
        self._active_person = None

        self.settings_change_callback = self.on_settings_changed
        TMDb().api_key = self.api_key

    @property
    def api_key(self):
        return self._api_key

    @api_key.setter
    def api_key(self, value):
        self._api_key = self.verify_api(value)

    @property
    def search_depth(self):
        return self._search_depth

    @search_depth.setter
    def search_depth(self, value):
        self._search_depth = int(value)

    @property
    def match_confidence(self):
        return self._match_confidence

    @match_confidence.setter
    def match_confidence(self, value):
        if value <= 1.0:
            self._match_confidence = float(value)

    # active_movie and active_person will help with conversational dialog I hope.
    @property
    def active_movie(self):
        return self._active_movie

    @active_movie.setter
    def active_movie(self, movie_id):
        self._active_movie = movie_id

    @property
    def active_person(self):
        return self._active_person

    @active_person.setter
    def active_person(self, person_id):
        self._active_person = person_id

    def _search_for_movie(self, movie):
        for m in Movie().search(movie):
            if fuzzy_match(m.title, movie) >= self.settings.get("match_confidence"):
                self.active_movie = m
                LOG.debug(f"Chosen movie: {self.active_movie.title}")
                break

    def _search_for_person(self, person):
        for p in Person().search(person):
            if fuzzy_match(p.name, person) >= self.settings.get("match_confidence"):
                self.active_person = p
                LOG.debug(f"active person: {self.active_person}")
                break

    def _create_dialog_list(self, dialog_list):
        # create a list
        i = []
        for item in dialog_list:
            i.append(item)
        dialog = ""
        last_item = i.pop()
        last_item = last_item.get("title", last_item.get("name"))
        for item in i:
            item = item.get("title", item.get("name"))
            dialog = dialog + item + ", "
        LOG.debug(f"final dialog is {dialog} and {last_item}")
        return dialog, last_item

    def on_settings_changed(self):
        self.api_key = self.settings.get("apiv3", self.api_key)
        self.search_depth = self.settings.get(
            "search_depth", self.search_depth)
        self.match_confidence = self.settings.get(
            "match_confidence", self.match_confidence)
        LOG.debug(f"settings changed to {self.settings}")

    def verify_api(self, api_key):
        # Do a quick search to verify the api_key
        try:
            TMDb().api_key = api_key
            p = Movie().popular()
            return api_key
        except Exception:
            self.speak_dialog("no.valid.api", {})
            # self.speak_dialog("fallback.api", {})

    @intent_handler("movie.description.intent")
    def handle_movie_description_intent(self, message):
        """ Gets the long version of the requested movie."""
        movie = message.data.get("movie")
        LOG.debug(f"requested description for movie {movie}")
        self._search_for_movie(movie)
        try:
            if self.active_movie:
                if self.active_movie.overview is not "":
                    self.speak_dialog("movie.description", {"movie": movie})
                    for sentence in self.active_movie.overview.split(". "):
                        self.speak(sentence)
                else:
                    self.speak_dialog(
                        "movie.description.error", {"movie": movie})
            else:
                self.speak_dialog("no.info", {"movie": movie})

        # If the title can not be found, it creates an IndexError
        except IndexError:
            self.speak_dialog("no.info", {"movie": movie})

    @intent_handler("movie.year.intent")
    def handle_movie_year(self, message):
        """ Gets the year the movie was released."""
        movie = message.data.get("movie")
        LOG.debug(f"requested year made for movie {movie}")
        self._search_for_movie(movie)
        try:
            if self.active_movie:
                if self.active_movie.release_date:
                    self.speak_dialog("movie.year", {"movie": self.active_movie.title, "year": nice_date(
                        datetime.strptime(self.active_movie.release_date.replace("-", " "), "%Y %m %d"))})
                else:
                    self.speak_dialog("movie.year.error", {
                                      "movie": self.active_movie.title})

        # If the title can not be found, it creates an IndexError
        except IndexError:
            self.speak_dialog("no.info", {"movie": movie})

    @intent_handler("movie.cast.intent")
    def handle_movie_cast(self, message):
        """ Gets the cast of the requested movie."""
        movie = message.data.get("movie")
        LOG.debug(f"requested cast for movie {movie}")
        self._search_for_movie(movie)
        try:
            if self.active_movie and self.active_movie.id:
                LOG.debug(f"active_movie {self.active_movie}")
                cast = []
                credits = Movie().credits(self.active_movie.id)
                LOG.debug(f"credits {credits}")
                for c in Movie().credits(self.active_movie.id)["cast"]:
                    cast.append(c)
                    if len(cast) >= self.search_depth:
                        break
                LOG.debug(f"{self.active_movie} cast: {cast}")
            # Create a list to store the cast to be included in the dialog
            actor_list, last_actor = self._create_dialog_list(cast)
            self.speak_dialog("movie.cast", {
                              "movie": movie, "actorlist": actor_list, "lastactor": last_actor})

        # If the title can not be found, it creates an IndexError
        except IndexError:
            self.speak_dialog("no.info", {"movie": movie})

    # TODO: Need to find this again. New API results don't return the same as before
    # @intent_handler("movie.production.intent")
    # def handle_movie_production(self, message):
    #     """ Gets the production companies that made the movie.
    #
    #     The search_depth setting is avaliable at home.mycroft.ai
    #     """
    #     movie = message.data.get("movie")
    #     LOG.debug(f"requested production for movie {movie}")
    #     self._search_for_movie(movie)
    #     try:
    #         if self.active_movie and self.active_movie.id:
    #
    #         movie_details = Movie().details(Movie().search(movie)[:1][0].id)
    #         companyList = movie_details.production_companies[:self.searchDepth]
    #
    #         # If there is only one production company, say the dialog differently
    #         if len(companyList) == 1:
    #             self.speak_dialog("movie.production.single", {"movie": movie, "company": companyList[0]["name"]})
    #         # If there is more, get the last in the list and set up the dialog
    #         if len(companyList) > 1:
    #             companies = ""
    #             lastCompany = companyList.pop()["name"]
    #             for company in companyList:
    #                 companies = companies + company["name"] + ", "
    #             self.speak_dialog("movie.production.multiple", {"companies": companies, "movie": movie, "lastcompany": lastCompany})
    #
    #     # If the title can not be found, it creates an IndexError
    #     except IndexError:
    #         self.speak_dialog("no.info", {"movie": movie})

    @intent_handler("movie.genres.intent")
    def handle_movie_genre(self, message):
        """ Gets the genres the movie belongs to."""
        movie = message.data.get("movie")
        LOG.debug(f"requested cast for movie {movie}")
        self._search_for_movie(movie)
        try:
            if self.active_movie and self.active_movie.id:
                genres = []
                for g in Movie().details(self.active_movie.id).genres:
                    genres.append(g)
                    if len(genres) >= self.search_depth:
                        break
                if len(genres) > 1:
                    genre_list, last_genre = self._create_dialog_list(genres)
                    self.speak_dialog("movie.genre.multiple", {
                                      "genrelist": genre_list, "genrelistlast": last_genre})
                else:
                    self.speak_dialog("movie.genre.single", {
                                      "movie": movie, "genre": genres[0].name})
        # If the title can not be found, it creates an IndexError
        except IndexError:
            self.speak_dialog("no.info", {"movie": movie})

    @intent_handler("movie.runtime.intent")
    def handle_movie_length(self, message):
        """ Gets the runtime of the searched movie."""
        movie = message.data.get("movie")
        LOG.debug(f"requested runtime for movie {movie}")
        self._search_for_movie(movie)
        try:
            if self.active_movie:
                movie_runtime = Movie().details(self.active_movie.id).runtime
                self.speak_dialog("movie.runtime", {
                                  "movie": movie, "runtime": movie_details.runtime})

        # If the title can not be found, it creates an IndexError
        except IndexError:
            self.speak_dialog("no.info", {"movie": movie})

    @intent_handler("movie.recommendations.intent")
    def handle_movie_recommendations(self, message):
        """ Gets the top movies that are similar to the suggested movie."""
        movie = message.data.get("movie")
        LOG.debug(f"requested recommendations like the movie {movie}")
        self._search_for_movie(movie)
        try:
            if self.active_movie:
                recommendation_list = []
                for r in Movie().recommendations(self.active_movie.id):
                    recommendation_list.append(r)
                    if len(recommendation_list) >= self.search_depth:
                        break
                movie_list, last_movie = self._create_dialog_list(
                    recommendation_list)

            self.speak_dialog("movie.recommendations", {
                              "movielist": movie_list, "lastmovie": last_movie, "movie": movie})

        # If the title can not be found, it creates an IndexError
        except IndexError:
            self.speak_dialog("no.info", {"movie": movie})

    @intent_handler("movie.popular.intent")
    def handle_popular_movies(self, message):
        """ Gets the daily popular movies.

        The list changes daily, and are not just recent movies.
        """
        try:
            movies = []
            for movie in Movie().popular():
                movies.append(movie)
                if len(movies) >= self.search_depth:
                    break
            # Lets see...I think we will set up the dialog again.
            popular_movies, last_movie = self._create_dialog_list(movies)
            self.speak_dialog("movie.popular", {
                              "popularlist": popular_movies, "lastmovie": last_movie})

        # If the title can not be found, it creates an IndexError
        except IndexError:
            self.speak_dialog("no.info", {"movie": movie})

    @intent_handler("movie.top.intent")
    def handle_top_movies(self, message):
        """ Gets the top rated movies of the day.
        The list changes daily, and are not just recent movies.
        """
        LOG.debug("requested the top movies playing")
        try:
            movies = Movie().top_rated()
            top_movies = []
            for m in movies:
                top_movies.append(m)
                if len(top_movies) >= self.search_depth:
                    break
            movie_list, last_movie = self._create_dialog_list(top_movies)
            self.speak_dialog(
                "movie.top", {"toplist": movie_list, "lastmovie": last_movie})

        # If the title can not be found, it creates an IndexError
        except IndexError:
            self.speak_dialog("no.info", {"movie": movie})
