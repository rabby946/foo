 in session:
        flash("welcome {user}")
        user_obj = User.get_user(user)
        render_template("user.html",user=user,player_name=user_obj.predicted_player if user_obj else None,
                           player_value=user_obj.predicted_value if user_obj else None,count=user_obj.predicted_count)
    flash("session timedout")