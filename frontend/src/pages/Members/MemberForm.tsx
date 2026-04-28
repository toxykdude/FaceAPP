/**
 * Member form for create/edit operations.
 */
import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Grid,
    FormControlLabel,
    Checkbox,
    MenuItem,
    Alert,
    Paper,
    Chip,
    InputAdornment,
    CircularProgress,
    useMediaQuery,
    useTheme,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions,
} from '@mui/material';
import { PhotoCamera, Edit as EditIcon, Delete as DeleteIcon } from '@mui/icons-material';
import { membersApi, MemberCreate, MemberUpdate } from '@/api/members';
import { membershipsApi } from '@/api/memberships';
import { membershipPlansApi, MembershipPlan } from '@/api/membershipPlans';
import { salesApi } from '@/api/sales';
import { addDays, format } from 'date-fns';
import { useLanguage } from '@/i18n/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';

const memberSchema = z.object({
    first_name: z.string().min(1, 'First name is required'),
    last_name: z.string().min(1, 'Last name is required'),
    email: z.string().optional().transform(v => v === '' ? undefined : v).pipe(z.string().email('Invalid email address').optional()),
    phone: z.string().optional(),
    id_number: z.string().optional(),
    date_of_birth: z.string().optional(),
    address: z.string().optional(),
    consent_given: z.boolean(),
    status: z.enum(['active', 'inactive', 'suspended']).optional(),
});

type MemberFormData = z.infer<typeof memberSchema>;

export const MemberForm: React.FC = () => {
    const navigate = useNavigate();
    const { id } = useParams();
    const queryClient = useQueryClient();
    const isEdit = !!id;
    const [createdMemberId, setCreatedMemberId] = React.useState<string | null>(null);
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

    const { data: member } = useQuery({
        queryKey: ['member', id],
        queryFn: () => membersApi.getMember(id!),
        enabled: isEdit,
    });

    const {
        control,
        handleSubmit,
        formState: { errors },
        reset,
    } = useForm<MemberFormData>({
        resolver: zodResolver(memberSchema),
        defaultValues: {
            first_name: '',
            last_name: '',
            email: '',
            phone: '',
            id_number: '',
            consent_given: false,
            status: 'active',
        },
    });

    // Populate form with member data when it loads in edit mode
    React.useEffect(() => {
        if (member) {
            reset({
                first_name: member.first_name || '',
                last_name: member.last_name || '',
                email: member.email || '',
                phone: member.phone || '',
                id_number: member.id_number || '',
                date_of_birth: member.date_of_birth || '',
                address: member.address || '',
                consent_given: member.consent_given || false,
                status: member.status || 'active',
            });
        }
    }, [member, reset]);

    const createMutation = useMutation({
        mutationFn: (data: MemberCreate) => membersApi.createMember(data),
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            setCreatedMemberId(data.id);
        },
        onError: (error: any) => {
            const detail = error?.response?.data?.detail || error?.message || 'Failed to create member';
            alert('Error creating member: ' + detail);
        },
    });

    const updateMutation = useMutation({
        mutationFn: (data: MemberUpdate) => membersApi.updateMember(id!, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            queryClient.invalidateQueries({ queryKey: ['member', id] });
            navigate('/members');
        },
    });

    const effectiveMemberId = id || createdMemberId;
    const showSubSections = isEdit || !!createdMemberId;

    const onSubmit = (data: MemberFormData) => {
        if (isEdit) {
            updateMutation.mutate(data);
        } else {
            createMutation.mutate(data as MemberCreate);
        }
    };

    return (
        <Box sx={{ px: { xs: 1, sm: 2, md: 3 } }}>
            <Typography variant={isMobile ? "h5" : "h4"} gutterBottom>
                {isEdit ? t.members.editMember : t.members.addMember}
            </Typography>

            {(!createdMemberId || isEdit) && (
            <Card>
                <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                    <form onSubmit={handleSubmit(onSubmit)}>
                        <Grid container spacing={2}>
                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="first_name"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.members.firstName}
                                            error={!!errors.first_name}
                                            helperText={errors.first_name?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="last_name"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.members.lastName}
                                            error={!!errors.last_name}
                                            helperText={errors.last_name?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="id_number"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.members.idNumber}
                                            placeholder="e.g. 12345678"
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="email"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.members.emailOptional}
                                            placeholder="email@example.com"
                                            error={!!errors.email}
                                            helperText={errors.email?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="phone"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.members.phone}
                                            error={!!errors.phone}
                                            helperText={errors.phone?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="date_of_birth"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.members.dateOfBirth}
                                            type="date"
                                            InputLabelProps={{ shrink: true }}
                                        />
                                    )}
                                />
                            </Grid>

                            {isEdit && (
                                <Grid item xs={12} sm={6}>
                                    <Controller
                                        name="status"
                                        control={control}
                                        render={({ field }) => (
                                            <TextField {...field} fullWidth select label={t.members.status}>
                                                <MenuItem value="active">{t.members.active}</MenuItem>
                                                <MenuItem value="inactive">{t.members.inactive}</MenuItem>
                                                <MenuItem value="suspended">{t.members.suspended}</MenuItem>
                                            </TextField>
                                        )}
                                    />
                                </Grid>
                            )}

                            <Grid item xs={12}>
                                <Controller
                                    name="address"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField {...field} fullWidth label={t.members.address} multiline rows={2} />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Controller
                                    name="consent_given"
                                    control={control}
                                    render={({ field }) => (
                                        <FormControlLabel
                                            control={<Checkbox {...field} checked={field.value} />}
                                            label={t.members.consentLabel}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Box display="flex" gap={2} flexDirection={{ xs: 'column', sm: 'row' }}>
                                    <Button type="submit" variant="contained" size="large" fullWidth={isMobile}>
                                        {isEdit ? t.members.update : t.members.create}
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        size="large"
                                        onClick={() => navigate('/members')}
                                        fullWidth={isMobile}
                                    >
                                        {t.members.cancel}
                                    </Button>
                                </Box>
                            </Grid>
                        </Grid>
                    </form>
                </CardContent>
            </Card>
            )}

            {/* Success message after creation */}
            {createdMemberId && !isEdit && (
                <Paper sx={{ p: 3, mb: 3, bgcolor: 'success.lighter', borderRadius: 2 }}>
                    <Typography variant="h6" color="success.main">✅ {t.members.memberCreated}</Typography>
                    <Typography variant="body2" color="textSecondary">
                        {t.members.memberCreatedSub}
                    </Typography>
                    <Button sx={{ mt: 1 }} onClick={() => navigate('/members')}>{t.members.skipToMembers}</Button>
                </Paper>
            )}

            {showSubSections && effectiveMemberId && <MembershipSection memberId={effectiveMemberId} />}
            {showSubSections && effectiveMemberId && <FaceEnrollmentSection memberId={effectiveMemberId} />}
        </Box>
    );
};

interface MembershipHistoryItem {
    id: string;
    member_id: string;
    plan_id?: string;
    type: string;
    start_date: string;
    end_date: string;
    price: number;
    status: 'active' | 'expired' | 'cancelled' | 'suspended';
    created_at: string;
    updated_at: string;
    plan_name?: string;
}

const MembershipSection: React.FC<{ memberId: string }> = ({ memberId }) => {
    const queryClient = useQueryClient();
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin';

    const [showForm, setShowForm] = React.useState(false);
    const [renewFromMembership, setRenewFromMembership] = React.useState<MembershipHistoryItem | null>(null);
    const [editingMembership, setEditingMembership] = React.useState<MembershipHistoryItem | null>(null);
    const [editStartDate, setEditStartDate] = React.useState('');
    const [editEndDate, setEditEndDate] = React.useState('');
    const [editPrice, setEditPrice] = React.useState('');
    const [selectedPlanId, setSelectedPlanId] = React.useState('');
    const [startDate, setStartDate] = React.useState(format(new Date(), 'yyyy-MM-dd'));
    const [paymentMethod, setPaymentMethod] = React.useState<'cash' | 'transfer'>('cash');
    const [paymentAmount, setPaymentAmount] = React.useState<string>('');
    const [deleteTarget, setDeleteTarget] = React.useState<MembershipHistoryItem | null>(null);
    const { data: memberships, isLoading: membershipsLoading } = useQuery({
        queryKey: ['memberships', 'member', memberId],
        queryFn: () => membershipsApi.getMemberships(0, 50, memberId),
    });

    const sortedMemberships = React.useMemo(() => {
        if (!memberships) return [];
        return [...memberships].sort((a, b) => new Date(b.end_date).getTime() - new Date(a.end_date).getTime());
    }, [memberships]);

    const { data: plansData } = useQuery({
        queryKey: ['membershipPlans', 'active'],
        queryFn: () => membershipPlansApi.getPlans(true)
    });
    const plans = plansData?.plans || [];

    const selectedPlan = plans.find((p: MembershipPlan) => p.id === selectedPlanId);

    const endDate = React.useMemo(() => {
        if (!selectedPlan || !startDate) return '';
        const start = new Date(startDate);
        const end = addDays(start, selectedPlan.duration_days || 0);
        return format(end, 'yyyy-MM-dd');
    }, [selectedPlanId, startDate, selectedPlan]);

    React.useEffect(() => {
        if (selectedPlan) {
            setPaymentAmount(String(selectedPlan.price));
        }
    }, [selectedPlanId, selectedPlan]);

    const price = selectedPlan ? Number(selectedPlan.price) : 0;
    const paidAmount = Number(paymentAmount) || 0;
    const isPartial = paidAmount < price && paidAmount > 0;
    const isPending = paidAmount === 0;
    const isPaid = paidAmount >= price;

    const createMutation = useMutation({
        mutationFn: async (data: any) => {
            const membership = await membershipsApi.createMembership(data.membership);
            if (data.payment.amount > 0) {
                await salesApi.createTransaction({
                    member_id: data.membership.member_id,
                    membership_id: membership.id,
                    amount: data.payment.amount,
                    payment_method: data.payment.method,
                    notes: data.payment.notes || undefined,
                });
            }
            return membership;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['memberships'] });
            queryClient.invalidateQueries({ queryKey: ['memberships', 'member', memberId] });
            setShowForm(false);
            setRenewFromMembership(null);
            setSelectedPlanId('');
            setPaymentAmount('');
            setPaymentMethod('cash');
            setStartDate(format(new Date(), 'yyyy-MM-dd'));
        },
        onError: (error: any) => {
            alert(`Error: ${error.response?.data?.detail || error.message}`);
        }
    });

    const editMutation = useMutation({
        mutationFn: async ({ id, data }: { id: string; data: any }) => {
            return await membershipsApi.updateMembership(id, data);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['memberships', 'member', memberId] });
            queryClient.invalidateQueries({ queryKey: ['memberships'] });
            queryClient.invalidateQueries({ queryKey: ['members'] });
            setEditingMembership(null);
        },
        onError: (error: any) => {
            alert('Error: ' + (error.response?.data?.detail || error.message));
        }
    });

    const deleteMutation = useMutation({
        mutationFn: async (membershipId: string) => {
            await membershipsApi.deleteMembership(membershipId);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['memberships', 'member', memberId] });
            queryClient.invalidateQueries({ queryKey: ['memberships'] });
            queryClient.invalidateQueries({ queryKey: ['members'] });
            setDeleteTarget(null);
        },
        onError: (error: any) => {
            alert('Error: ' + (error.response?.data?.detail || error.message));
        }
    });

    const handleEdit = (membership: MembershipHistoryItem) => {
        setEditingMembership(membership);
        setEditStartDate(membership.start_date);
        setEditEndDate(membership.end_date);
        setEditPrice(String(membership.price));
    };

    const handleSaveEdit = () => {
        if (!editingMembership) return;
        editMutation.mutate({
            id: editingMembership.id,
            data: {
                start_date: editStartDate,
                end_date: editEndDate,
                price: Number(editPrice),
            }
        });
    };

    const handleCancelEdit = () => {
        setEditingMembership(null);
        setEditStartDate('');
        setEditEndDate('');
        setEditPrice('');
    };

    const handleAssign = () => {
        if (!selectedPlan) return;
        createMutation.mutate({
            membership: {
                member_id: memberId,
                plan_id: selectedPlanId,
                type: selectedPlan.name,
                start_date: startDate,
                end_date: endDate,
                price: price,
            },
            payment: {
                amount: paidAmount,
                method: paymentMethod,
                notes: isPartial ? `Pago parcial. Pendiente: $${price - paidAmount}` : 'Pago completo',
            }
        });
    };

    const handleRenew = (membership: MembershipHistoryItem) => {
        setRenewFromMembership(membership);
        if (membership.plan_id) {
            setSelectedPlanId(membership.plan_id);
        }
        const nextDay = addDays(new Date(membership.end_date + 'T12:00:00'), 1);
        setStartDate(format(nextDay, 'yyyy-MM-dd'));
        setPaymentMethod('cash');
        setShowForm(true);
    };

    const handleAddNew = () => {
        setRenewFromMembership(null);
        setSelectedPlanId('');
        setStartDate(format(new Date(), 'yyyy-MM-dd'));
        setPaymentAmount('');
        setPaymentMethod('cash');
        setShowForm(true);
    };

    const handleCancelForm = () => {
        setShowForm(false);
        setRenewFromMembership(null);
        setSelectedPlanId('');
        setPaymentAmount('');
        setPaymentMethod('cash');
        setStartDate(format(new Date(), 'yyyy-MM-dd'));
    };

    const formatPlanLabel = (plan: MembershipPlan) => {
        const durationParts: string[] = [];
        if (plan.duration_months) durationParts.push(`${plan.duration_months}m`);
        if (plan.duration_days) durationParts.push(`${plan.duration_days}d`);
        const durationStr = durationParts.join(' ') || '0d';
        return `${plan.name} — $${Number(plan.price).toLocaleString()} (${durationStr})`;
    };

    const formatDate = (dateStr: string) => {
        try {
            return format(new Date(dateStr + 'T12:00:00'), 'MMM d, yyyy');
        } catch {
            return dateStr;
        }
    };

    const getStatusChip = (status: string) => {
        switch (status) {
            case 'active':
                return <Chip label={t.members.active} color="success" size="small" icon={<span>{'\u2705'}</span>} />;
            case 'expired':
                return <Chip label={t.members.expired} color="error" size="small" icon={<span>{'\u26d4'}</span>} />;
            case 'cancelled':
                return <Chip label={t.memberships.cancelled} color="default" size="small" icon={<span>{'\ud83d\udeab'}</span>} />;
            case 'suspended':
                return <Chip label={t.members.suspended} color="warning" size="small" icon={<span>{'\u23f8\ufe0f'}</span>} />;
            default:
                return <Chip label={status} size="small" />;
        }
    };

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                <Typography variant="h6" gutterBottom>{t.members.membershipHistory}</Typography>

                {membershipsLoading && (
                    <Box display="flex" justifyContent="center" p={3}>
                        <CircularProgress size={24} />
                    </Box>
                )}

                {!showForm && !membershipsLoading && (
                    <>
                        {sortedMemberships.length === 0 ? (
                            <Typography variant="body2" color="textSecondary" sx={{ py: 2 }}>
                                {t.members.noMembershipsFound}
                            </Typography>
                        ) : (
                            <Box display="flex" flexDirection="column" gap={1.5}>
                                {sortedMemberships.map((m) => (
                                    <Paper
                                        key={m.id}
                                        variant="outlined"
                                        sx={{
                                            p: 2,
                                            display: 'flex',
                                            flexDirection: { xs: 'column', sm: 'row' },
                                            alignItems: { xs: 'flex-start', sm: 'center' },
                                            justifyContent: 'space-between',
                                            gap: 2,
                                        }}
                                    >
                                        <Box sx={{ flex: 1 }}>
                                            <Box display="flex" alignItems="center" gap={1} mb={0.5} flexWrap="wrap">
                                                <Typography variant="subtitle1" fontWeight="bold">
                                                    {m.plan_name || m.type}
                                                </Typography>
                                                {getStatusChip(m.status)}
                                            </Box>
                                            {editingMembership?.id === m.id ? (
                                                <Box display="flex" flexDirection="column" gap={1.5} mt={1} mb={0.5}>
                                                    <Typography variant="caption" color="textSecondary">
                                                        {t.members.editDatesDesc}
                                                    </Typography>
                                                    <Grid container spacing={1}>
                                                        <Grid item xs={6}>
                                                            <TextField
                                                                label={t.members.startDate}
                                                                type="date"
                                                                value={editStartDate}
                                                                onChange={(e) => setEditStartDate(e.target.value)}
                                                                fullWidth
                                                                size="small"
                                                                InputLabelProps={{ shrink: true }}
                                                            />
                                                        </Grid>
                                                        <Grid item xs={6}>
                                                            <TextField
                                                                label={t.members.endDate}
                                                                type="date"
                                                                value={editEndDate}
                                                                onChange={(e) => setEditEndDate(e.target.value)}
                                                                fullWidth
                                                                size="small"
                                                                InputLabelProps={{ shrink: true }}
                                                            />
                                                        </Grid>
                                                        <Grid item xs={12}>
                                                            <TextField
                                                                label={t.members.planPrice}
                                                                type="number"
                                                                value={editPrice}
                                                                onChange={(e) => setEditPrice(e.target.value)}
                                                                fullWidth
                                                                size="small"
                                                                InputProps={{
                                                                    startAdornment: <InputAdornment position="start">$</InputAdornment>,
                                                                }}
                                                            />
                                                        </Grid>
                                                    </Grid>
                                                    <Box display="flex" gap={1} justifyContent="flex-end">
                                                        <Button
                                                            size="small"
                                                            variant="text"
                                                            onClick={handleCancelEdit}
                                                            sx={{ minHeight: 36 }}
                                                        >
                                                            {t.members.cancel}
                                                        </Button>
                                                        <Button
                                                            size="small"
                                                            variant="contained"
                                                            onClick={handleSaveEdit}
                                                            disabled={editMutation.isPending}
                                                            sx={{ minHeight: 36 }}
                                                        >
                                                            {editMutation.isPending ? '...' : t.members.saveChanges}
                                                        </Button>
                                                    </Box>
                                                </Box>
                                            ) : (
                                                <>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {formatDate(m.start_date)} {'\u2192'} {formatDate(m.end_date)}
                                                    </Typography>
                                                    <Typography variant="body2" fontWeight="500">
                                                        ${Number(m.price).toLocaleString()}
                                                    </Typography>
                                                </>
                                            )}
                                        </Box>
                                        {editingMembership?.id !== m.id && (
                                            <Box display="flex" gap={1} flexShrink={0}>
                                                {isAdmin && (
                                                    <Button
                                                        variant="outlined"
                                                        size="small"
                                                        color="primary"
                                                        onClick={() => handleEdit(m)}
                                                        sx={{ minWidth: 36, minHeight: 44, px: 1 }}
                                                    >
                                                        <EditIcon fontSize="small" />
                                                    </Button>
                                                )}
                                                {isAdmin && (
                                                    <Button
                                                        variant="outlined"
                                                        size="small"
                                                        color="error"
                                                        onClick={() => setDeleteTarget(m)}
                                                        sx={{ minWidth: 36, minHeight: 44, px: 1 }}
                                                    >
                                                        <DeleteIcon fontSize="small" />
                                                    </Button>
                                                )}
                                                <Button
                                                    variant="outlined"
                                                    size="small"
                                                    color={m.status === 'active' ? 'success' : m.status === 'expired' ? 'warning' : 'primary'}
                                                    onClick={() => handleRenew(m)}
                                                    sx={{ minWidth: 44, minHeight: 44 }}
                                                >
                                                    {t.members.renew}
                                                </Button>
                                            </Box>
                                        )}
                                    </Paper>
                                ))}
                            </Box>
                        )}

                        <Button
                            variant="text"
                            startIcon={<span>+</span>}
                            onClick={handleAddNew}
                            sx={{ mt: 2 }}
                        >
                            {t.members.addNew}
                        </Button>
                    </>
                )}

                {showForm && (
                    <>
                        <Box display="flex" alignItems="center" gap={1} mb={2}>
                            <Typography variant="subtitle1" fontWeight="bold">
                                {renewFromMembership ? t.members.renewMembership : t.members.assignNew}
                            </Typography>
                            {renewFromMembership && getStatusChip(renewFromMembership.status)}
                        </Box>

                        {renewFromMembership && (
                            <Alert severity="info" sx={{ mb: 2 }}>
                                {t.members.renewingFrom} <strong>{renewFromMembership.plan_name || renewFromMembership.type}</strong> —
                                {' '}{t.members.previousMembership}: {formatDate(renewFromMembership.start_date)} → {formatDate(renewFromMembership.end_date)}
                            </Alert>
                        )}

                        <Box display="flex" flexDirection="column" gap={2}>
                            <TextField
                                select
                                label={t.members.selectPlan}
                                value={selectedPlanId}
                                onChange={(e) => setSelectedPlanId(e.target.value)}
                                fullWidth
                                required
                            >
                                <MenuItem value=""><em>{t.members.choosePlan}</em></MenuItem>
                                {plans.map((plan: MembershipPlan) => (
                                    <MenuItem key={plan.id} value={plan.id}>
                                        {formatPlanLabel(plan)}
                                    </MenuItem>
                                ))}
                            </TextField>

                            <Grid container spacing={2}>
                                <Grid item xs={12} sm={6}>
                                    <TextField
                                        label={t.members.startDate}
                                        type="date"
                                        value={startDate}
                                        onChange={(e) => setStartDate(e.target.value)}
                                        fullWidth
                                        InputLabelProps={{ shrink: true }}
                                    />
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <TextField
                                        label={t.members.endDate}
                                        type="date"
                                        value={endDate}
                                        fullWidth
                                        InputLabelProps={{ shrink: true }}
                                        InputProps={{ readOnly: true }}
                                        helperText={t.members.endAutoCalc}
                                        sx={{ '& .MuiInputBase-input': { color: 'text.secondary' } }}
                                    />
                                </Grid>
                            </Grid>

                            {selectedPlan && (
                                <TextField
                                    label={t.members.planPrice}
                                    value={`$${price.toLocaleString()}`}
                                    fullWidth
                                    InputProps={{ readOnly: true }}
                                    sx={{ '& .MuiInputBase-input': { fontWeight: 'bold', fontSize: '1.1rem' } }}
                                />
                            )}

                            {selectedPlan && (
                                <>
                                    <TextField
                                        select
                                        label={t.members.paymentMethod}
                                        value={paymentMethod}
                                        onChange={(e) => setPaymentMethod(e.target.value as 'cash' | 'transfer')}
                                        fullWidth
                                    >
                                        <MenuItem value="cash">{'\ud83d\udcb5'} {t.members.cash}</MenuItem>
                                        <MenuItem value="transfer">{'\ud83c\udfe6'} {t.members.transfer}</MenuItem>
                                    </TextField>

                                    <TextField
                                        label={t.members.paymentAmount}
                                        type="number"
                                        value={paymentAmount}
                                        onChange={(e) => setPaymentAmount(e.target.value)}
                                        fullWidth
                                        InputProps={{
                                            startAdornment: <InputAdornment position="start">$</InputAdornment>,
                                        }}
                                        helperText={
                                            isPaid ? "✅ " + t.members.paymentComplete :
                                            isPartial ? "⚠️ " + t.members.paymentPartial.replace('${amount}', `$${(price - paidAmount).toLocaleString()}`) :
                                            "❌ " + t.members.noPayment
                                        }
                                    />

                                    <Box>
                                        {isPaid && <Chip label={t.members.paid} color="success" />}
                                        {isPartial && <Chip label={`${t.members.partial}: $${paidAmount.toLocaleString()} de $${price.toLocaleString()}`} color="warning" />}
                                        {isPending && <Chip label={t.members.pending} color="error" />}
                                    </Box>
                                </>
                            )}

                            <Box display="flex" gap={2} flexDirection={{ xs: 'column', sm: 'row' }}>
                                <Button
                                    onClick={handleAssign}
                                    variant="contained"
                                    size="large"
                                    disabled={!selectedPlanId || createMutation.isPending}
                                    fullWidth={isMobile}
                                    sx={{ minHeight: 44 }}
                                >
                                    {createMutation.isPending ? t.members.assigning : t.members.assignMembershipBtn}
                                </Button>
                                <Button
                                    onClick={handleCancelForm}
                                    variant="outlined"
                                    size="large"
                                    fullWidth={isMobile}
                                    sx={{ minHeight: 44 }}
                                >
                                    {t.members.cancel}
                                </Button>
                            </Box>
                        </Box>
                    </>
                )}
            </CardContent>

            {/* Delete Membership Confirmation Dialog — Admin only */}
            <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} fullWidth fullScreen={isMobile}>
                <DialogTitle>{t.members.deleteMembership}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t.members.deleteMembershipConfirm}
                    </DialogContentText>
                    {deleteTarget && (
                        <Box mt={2} p={2} bgcolor="grey.100" borderRadius={1}>
                            <Typography variant="body2">
                                <strong>{deleteTarget.plan_name || deleteTarget.type}</strong>
                            </Typography>
                            <Typography variant="body2" color="textSecondary">
                                {formatDate(deleteTarget.start_date)} → {formatDate(deleteTarget.end_date)}
                            </Typography>
                            <Typography variant="body2" fontWeight="500">
                                ${Number(deleteTarget.price).toLocaleString()}
                            </Typography>
                        </Box>
                    )}
                </DialogContent>
                <DialogActions sx={{ p: { xs: 2, sm: 3 }, flexDirection: { xs: 'column', sm: 'row' }, gap: 1 }}>
                    <Button onClick={() => setDeleteTarget(null)} fullWidth={isMobile}>{t.members.cancel}</Button>
                    <Button
                        onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
                        color="error"
                        variant="contained"
                        disabled={deleteMutation.isPending}
                        fullWidth={isMobile}
                    >
                        {deleteMutation.isPending ? t.members.deleting : t.members.delete}
                    </Button>
                </DialogActions>
            </Dialog>
        </Card>
    );
};

const FaceEnrollmentSection: React.FC<{ memberId: string }> = ({ memberId }) => {
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const [enrollmentStatus, setEnrollmentStatus] = React.useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
    const [qualityScore, setQualityScore] = React.useState<number | null>(null);
    const [errorMsg, setErrorMsg] = React.useState<string>('');
    const [cameraActive, setCameraActive] = React.useState(false);
    const [stream, setStream] = React.useState<MediaStream | null>(null);
    const fileInputRef = React.useRef<HTMLInputElement>(null);
    const videoRef = React.useRef<HTMLVideoElement>(null);
    const canvasRef = React.useRef<HTMLCanvasElement>(null);

    const enrollWithFile = async (file: File) => {
        setEnrollmentStatus('uploading');
        setErrorMsg('');
        try {
            const result = await membersApi.enrollBiometric(memberId, file);
            setQualityScore(result.quality_score);
            setEnrollmentStatus('success');
        } catch (error: any) {
            const detail = error?.response?.data?.detail || error?.message || 'Unknown error';
            setErrorMsg(detail);
            setEnrollmentStatus('error');
        }
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        await enrollWithFile(file);
    };

    const startCamera = async () => {
        try {
            const mediaStream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480, facingMode: 'user' }
            });
            setStream(mediaStream);
            setCameraActive(true);
            setErrorMsg('');
            setTimeout(() => {
                if (videoRef.current) {
                    videoRef.current.srcObject = mediaStream;
                }
            }, 100);
        } catch (err: any) {
            setErrorMsg('Could not access camera: ' + (err.message || 'Permission denied'));
            setEnrollmentStatus('error');
        }
    };

    const stopCamera = () => {
        if (stream) {
            stream.getTracks().forEach(t => t.stop());
        }
        setStream(null);
        setCameraActive(false);
    };

    const captureAndEnroll = async () => {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!video || !canvas) return;

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.drawImage(video, 0, 0);
        stopCamera();

        canvas.toBlob(async (blob) => {
            if (!blob) return;
            const file = new File([blob], 'webcam-capture.jpg', { type: 'image/jpeg' });
            await enrollWithFile(file);
        }, 'image/jpeg', 0.92);
    };

    React.useEffect(() => {
        return () => {
            if (stream) stream.getTracks().forEach(t => t.stop());
        };
    }, []);

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                <Typography variant="h6" gutterBottom>{t.members.faceEnrollment}</Typography>

                {enrollmentStatus === 'success' ? (
                    <Alert severity="success">
                        {t.members.enrolledSuccess} Quality score: {qualityScore?.toFixed(2)}
                    </Alert>
                ) : (
                    <Box>
                        <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                            {t.members.enrollBiometric}
                        </Typography>

                        {cameraActive && (
                            <Box sx={{ mb: 2, position: 'relative' }}>
                                <video
                                    ref={videoRef}
                                    autoPlay
                                    playsInline
                                    muted
                                    style={{
                                        width: '100%',
                                        maxWidth: 480,
                                        borderRadius: 8,
                                        border: '2px solid',
                                        borderColor: 'primary.main',
                                    }}
                                />
                                <Box display="flex" gap={1} mt={1} flexDirection={{ xs: 'column', sm: 'row' }}>
                                    <Button
                                        variant="contained"
                                        color="primary"
                                        onClick={captureAndEnroll}
                                        disabled={enrollmentStatus === 'uploading'}
                                        fullWidth={isMobile}
                                        sx={{ minHeight: 44 }}
                                    >
                                        {enrollmentStatus === 'uploading' ? t.members.processing : `📸 ${t.members.captureEnroll}`}
                                    </Button>
                                    <Button variant="outlined" color="error" onClick={stopCamera} fullWidth={isMobile} sx={{ minHeight: 44 }}>
                                        {t.members.cancel}
                                    </Button>
                                </Box>
                            </Box>
                        )}

                        {!cameraActive && (
                            <Box display="flex" gap={2} flexWrap="wrap" flexDirection={{ xs: 'column', sm: 'row' }}>
                                <Button
                                    variant="contained"
                                    startIcon={<PhotoCamera />}
                                    onClick={startCamera}
                                    disabled={enrollmentStatus === 'uploading'}
                                    fullWidth={isMobile}
                                    sx={{ minHeight: 44 }}
                                >
                                    {t.members.useWebcam}
                                </Button>
                                <Button
                                    variant="outlined"
                                    startIcon={<PhotoCamera />}
                                    onClick={() => fileInputRef.current?.click()}
                                    disabled={enrollmentStatus === 'uploading'}
                                    fullWidth={isMobile}
                                    sx={{ minHeight: 44 }}
                                >
                                    {enrollmentStatus === 'uploading' ? t.members.processing : t.members.uploadPhoto}
                                </Button>
                                <input
                                    type="file"
                                    accept="image/*"
                                    onChange={handleFileUpload}
                                    ref={fileInputRef}
                                    style={{ display: 'none' }}
                                />
                            </Box>
                        )}

                        <canvas ref={canvasRef} style={{ display: 'none' }} />

                        {enrollmentStatus === 'error' && errorMsg && (
                            <Alert severity="error" sx={{ mt: 2 }}>
                                {errorMsg}
                            </Alert>
                        )}

                        {enrollmentStatus === 'uploading' && !cameraActive && (
                            <Box display="flex" alignItems="center" gap={1} mt={2}>
                                <CircularProgress size={20} />
                                <Typography variant="body2">{t.members.processingEnrollment}</Typography>
                            </Box>
                        )}
                    </Box>
                )}
            </CardContent>
        </Card>
    );
};
