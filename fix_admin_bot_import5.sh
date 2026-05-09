sed -i '/from cache import redis_client, set_fsm_state/s/$/ , acquire_lock, release_lock/' modules/admin.py
sed -i '/from database import get_all_users/s/$/ , get_user, update_user/' modules/admin.py
sed -i '/from modules.utils import (/a\    get_fsm_step,' modules/admin.py
