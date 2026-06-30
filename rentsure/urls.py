"""
URL configuration for rentsure project.
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView
from django.views.generic import RedirectView

# Import views
from properties import views as property_views
from users import views as user_views
from payments import views as payments_views
from security import views as security_views
from properties import views


urlpatterns = [
    # ====================== ADMIN & CORE ======================
    path('admin/', admin.site.urls),
    path('', property_views.home, name='home'),

    # ====================== AUTHENTICATION ======================
    path('register/', user_views.register, name='register'),
    path('login/', user_views.login_view, name='login'),
    path('logout/', user_views.logout_view, name='logout'),

    # Password Reset
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'), name='password_reset_complete'),

    # ====================== STATIC PAGES ======================
    path('how-it-works/', cache_page(60 * 60)(property_views.how_it_works), name='how_it_works'),
    path('safety-tips/', cache_page(60 * 60)(property_views.safety_tips), name='safety_tips'),
    path('safety/', RedirectView.as_view(url='/safety-tips/', permanent=True), name='safety_redirect'),
    path('terms/', TemplateView.as_view(template_name='static_pages/terms_of_service.html'), name='terms'),
    path('privacy/', TemplateView.as_view(template_name='static_pages/privacy_policy.html'), name='privacy'),

    # ====================== PROPERTIES ======================
    path('search/', property_views.search, name='search'),
    path('properties/', property_views.property_list, name='property_list'),
    path('property/<int:pk>/', property_views.property_detail, name='property_detail'),
    path('create/', property_views.create_property, name='create_property'),

   # Property Management
    path('<int:property_id>/images/', views.manage_property_images, name='manage_property_images'),
    path('<int:property_id>/units/', views.manage_units, name='manage_units'),    
    path('<int:property_id>/add-unit/', views.add_unit, name='add_unit'),
    path('<int:property_id>/edit-unit/<int:unit_id>/', views.edit_unit, name='edit_unit'),
    path('<int:property_id>/delete-unit/<int:unit_id>/', views.delete_unit, name='delete_unit'),
    path('property/<int:pk>/edit/', property_views.edit_property, name='edit_property'),
    path('property/<int:property_id>/delete/', property_views.delete_property, name='delete_property'),

    # Reviews & Interactions
    path('property/<int:property_id>/review/', property_views.add_review, name='add_review'),
    path('property/<int:property_id>/save/', property_views.toggle_save_property, name='toggle_save_property'),

    # Compare & Favorites
    path('compare/add/<int:unit_id>/', views.add_to_compare, name='add_to_compare'),
    path('compare/remove/<int:unit_id>/', views.remove_from_compare, name='remove_from_compare'),
    path('compare/', views.compare, name='compare'),
    path('favorite-estate/add/', property_views.add_favorite_estate, name='add_favorite_estate'),
    path('favorite-estate/remove/<int:estate_id>/', property_views.remove_favorite_estate, name='remove_favorite_estate'),

    # Scam Report
    path('report-scam/<int:property_id>/', property_views.report_scam, name='report_scam'),
    path('report-scam/', property_views.report_scam, name='report_scam'),

    # ====================== VIEWINGS ======================
    path('property/<int:property_id>/request-viewing/', property_views.request_viewing, name='request_viewing'),
    path('manage-viewings/', property_views.manage_viewings, name='manage_viewings'),
    path('appointment/<int:appointment_id>/<str:status>/', property_views.update_appointment_status, name='update_appointment_status'),
    path('appointment/<int:appointment_id>/cancel/', property_views.cancel_appointment, name='cancel_appointment'),
    path('appointment/qr/<int:appointment_id>/', property_views.appointment_qr, name='appointment_qr'),
    path('appointment/checkin/<int:appointment_id>/', property_views.qr_checkin, name='qr_checkin'),

    # ====================== CHAT & NOTIFICATIONS ======================
    path('chats/', property_views.chat_list, name='chat_list'),
    path('chat/property/<int:property_id>/', property_views.chat_detail, name='chat_detail'),
    path('chat/property/<int:property_id>/user/<int:user_id>/', property_views.chat_detail, name='chat_detail_with_user'),

    path('unread-messages/', property_views.unread_message_count, name='unread_message_count'),
    path('notifications/', property_views.notifications_list, name='notification_list'),
    path('unread-notifications/', property_views.unread_notifications_count, name='unread_notifications_count'),
    path('notifications/mark/<int:notification_id>/', property_views.mark_notification_read, name='mark_notification_read'),
    path('notifications/delete/<int:notification_id>/', property_views.delete_notification, name='delete_notification'),
    path('notifications/mark-all/', property_views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/delete-all/', property_views.delete_all_notifications, name='delete_all_notifications'),

    # ====================== USER PROFILE ======================
    path('dashboard/', user_views.dashboard, name='dashboard'),
    path('profile/', user_views.profile_settings, name='profile'),
    path('settings/', user_views.profile_settings, name='profile_settings'),
    path('verify/', user_views.verification_center, name='verification_center'),
    path('kyc/', user_views.kyc_submit, name='kyc_submit'),
    path('update-location/', user_views.update_location, name='update_location'),
    path('set-default-location/', user_views.set_default_location, name='set_default_location'),

    path('testimonial/', user_views.submit_testimonial, name='submit_testimonial'),
    path('app-lead/', user_views.app_lead, name='app_lead'),

    # ====================== PAYMENTS & ESCROW ======================
    path('pay-listing/<int:property_id>/', payments_views.pay_listing_fee, name='pay_listing_fee'),
    path('mpesa-callback/', payments_views.mpesa_callback, name='mpesa_callback'),
    

    path('escrow/initiate/<int:property_id>/', payments_views.initiate_escrow, name='initiate_escrow'),
    path('escrow/initiate/<int:property_id>/unit/<int:unit_id>/', payments_views.initiate_escrow, name='initiate_escrow_unit'),
    path('escrow/status/<int:escrow_id>/', payments_views.escrow_status, name='escrow_status'),
    path('escrow/release/<int:escrow_id>/', payments_views.release_escrow, name='release_escrow'),
    path('escrow/confirm/<int:escrow_id>/', payments_views.confirm_move_in, name='confirm_move_in'),
    path('escrow/dispute/<int:escrow_id>/', payments_views.raise_dispute, name='raise_dispute'),
    path('dispute-chat/<int:escrow_id>/', payments_views.tenant_dispute_chat, name='tenant_dispute_chat'),

    # ====================== ADMIN & SECURITY ======================
    path('admin-analytics/', user_views.admin_dashboard, name='admin_analytics'),
    path('api/device-fingerprint/', security_views.device_fingerprint, name='device_fingerprint'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)